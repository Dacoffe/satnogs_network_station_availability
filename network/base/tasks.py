"""SatNOGS Network Celery task functions"""
import copy
import logging
import math
import os
import struct
import zipfile
from datetime import datetime, timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Max, Q
from django.db.models.signals import post_save
from django.utils.timezone import now
from internetarchive import upload
from internetarchive.exceptions import AuthenticationError
from tinytag import TinyTag
from tinytag.tinytag import TinyTagException

from network.base.db_api import DBConnectionError, get_tle_sets_by_sat_id_set, \
    get_transmitters_by_uuid_set
from network.base.models import DemodData, Observation, Station
from network.base.rating_tasks import rate_observation
from network.base.signals import _station_post_save
from network.base.utils import format_frequency, format_frequency_range, sync_demoddata_to_db
from network.base.validators import is_transmitter_in_station_range

LOGGER = logging.getLogger('db')


def get_and_refresh_transmitters_with_stats_cache(in_list_form=False):
    """Refreshes the cache of transmitters with associated statistics and returns them"""
    queryset = Observation.objects.order_by().values(
        'sat_id', 'transmitter_uuid', 'transmitter_downlink_low', 'transmitter_downlink_high',
        'transmitter_type'
    ).distinct().annotate(
        date=Max('end'),
        future=Count('pk', filter=Q(end__gt=now())),
        bad=Count('pk', filter=Q(status__range=(-100, -1))),
        unknown=Count('pk', filter=Q(status__range=(0, 99), end__lte=now())),
        good=Count('pk', filter=Q(status__gte=100)),
    )
    object_dict = {}
    sats = cache.get('satellites') or fetch_satellites()
    for transmitter in queryset:
        same_transmitter = object_dict.get(transmitter["transmitter_uuid"])
        if same_transmitter and same_transmitter["date"] > transmitter["date"]:
            continue
        sat = sats[transmitter['sat_id']]
        if sat.get('merged_into'):  # This sat_id was merged into another satellite
            continue
        transmitter['satellite__norad_cat_id'] = sat['norad_cat_id']
        transmitter['satellite__name'] = sat['name']
        total_count = 0
        unknown_count = transmitter['unknown'] or 0
        future_count = transmitter['future'] or 0
        good_count = transmitter['good'] or 0
        bad_count = transmitter['bad'] or 0
        total_count = unknown_count + future_count + good_count + bad_count
        unknown_rate = 0
        future_rate = 0
        success_rate = 0
        bad_rate = 0

        if total_count:
            unknown_rate = math.trunc(10000 * (unknown_count / total_count)) / 100
            future_rate = math.trunc(10000 * (future_count / total_count)) / 100
            success_rate = math.trunc(10000 * (good_count / total_count)) / 100
            bad_rate = math.trunc(10000 * (bad_count / total_count)) / 100

        transmitter['stats'] = {
            'total_count': int(total_count),
            'unknown_count': int(unknown_count),
            'future_count': int(future_count),
            'good_count': int(good_count),
            'bad_count': int(bad_count),
            'unknown_rate': int(unknown_rate),
            'future_rate': int(future_rate),
            'success_rate': int(success_rate),
            'bad_rate': int(bad_rate)
        }

        if transmitter['transmitter_type'] == 'Transponder' or transmitter[
                'transmitter_type'] == 'Range transmitter':
            transmitter['transmitter_freq'] = format_frequency_range(
                transmitter["transmitter_downlink_low"] or 0,
                transmitter["transmitter_downlink_high"] or 0
            )
        else:
            transmitter['transmitter_freq'] = format_frequency(
                transmitter["transmitter_downlink_low"] or 0
            )
        object_dict[transmitter['transmitter_uuid']] = transmitter
    cache.set('transmitters-with-stats', object_dict, 5 * 3600)
    return object_dict if not in_list_form else object_dict.values()


def delay_task_with_lock(task, lock_id, lock_expiration, *args):
    """Ensure unique run of a task by aquiring lock"""
    if cache.add('{0}-{1}'.format(task.name, lock_id), '', lock_expiration):
        task.delay(*args)


def get_observation_zip_group(observation_id):
    """ Return observation group """
    return (observation_id - 1) // settings.AUDIO_FILES_PER_ZIP


def get_zip_range_and_path(group):
    """ Return range and zip filepath for a group of observation IDs """
    group *= settings.AUDIO_FILES_PER_ZIP
    group_range = (group + 1, group + settings.AUDIO_FILES_PER_ZIP)
    zip_range = '{0}-{1}'.format(str(group_range[0]).zfill(9), str(group_range[1]).zfill(9))
    zip_filename = '{0}-{1}.zip'.format(settings.ZIP_FILE_PREFIX, zip_range)
    zip_path = '{0}/{1}'.format(settings.MEDIA_ROOT, zip_filename)
    return (group_range, zip_path)


@shared_task
def zip_audio(observation_id, path):
    """Add audio file to a zip file"""
    LOGGER.info('zip audio: %s', observation_id)
    group = get_observation_zip_group(observation_id)
    group_range, zip_path = get_zip_range_and_path(group)
    cache_key = '{0}-{1}-{2}'.format('ziplock', group_range[0], group_range[1])
    if cache.add(cache_key, '', settings.ZIP_AUDIO_LOCK_EXPIRATION):
        LOGGER.info('Lock acquired for zip audio: %s', observation_id)
        file_exists_in_zip_file = False
        files_in_zip = []
        if zipfile.is_zipfile(zip_path):
            with zipfile.ZipFile(file=zip_path, mode='r') as zip_file:
                files_in_zip = zip_file.namelist()
                filename = path.split('/')[-1]
                if filename in files_in_zip:
                    file_exists_in_zip_file = True
        if file_exists_in_zip_file:
            LOGGER.info('Audio file already exists in zip file for id %s', observation_id)
            ids = [name.split('_')[1] for name in files_in_zip]
            observations = Observation.objects.filter(pk__in=ids).exclude(payload=''
                                                                          ).exclude(archived=True)
            if observations.count() == len(ids):
                observations.update(audio_zipped=False)
                os.remove(zip_path)
            else:
                cache.delete(cache_key)
                error_message = (
                    'Zip file can not be deleted,'
                    ' it includes removed, archived or duplicate audio files'
                )
                raise RuntimeError(error_message)
        else:
            with zipfile.ZipFile(file=zip_path, mode='a', compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as zip_file:
                zip_file.write(filename=path, arcname=path.split('/')[-1])
            Observation.objects.filter(pk=observation_id).update(audio_zipped=True)
        cache.delete(cache_key)


@shared_task
def process_audio(observation_id, force_zip=False):
    """
    Process Audio
    * Check audio file for duration less than 1 sec
    * Validate audio file
    * Run task for rating according to audio file
    * Run task for adding audio in zip file
    """
    LOGGER.info('process audio: %s', observation_id)
    observations = Observation.objects.select_for_update()
    with transaction.atomic():
        observation = observations.get(pk=observation_id)
        try:
            audio_metadata = TinyTag.get(observation.payload.path)
            # Remove audio if it is less than 1 sec
            if audio_metadata.duration is None or audio_metadata.duration < 1:
                observation.payload.delete()
                return
            rate_observation(observation_id, 'audio_upload', audio_metadata.duration)
            if (settings.ZIP_AUDIO_FILES or force_zip) and not settings.USE_S3_STORAGE_FOR_AUDIO:
                zip_audio(observation_id, observation.payload.path)
        except TinyTagException:
            # Remove invalid audio file
            observation.payload.delete()
            return
        except (struct.error, TypeError):
            # Remove audio file with wrong structure
            observation.payload.delete()
            return


@shared_task
def zip_audio_files(force_zip=False):
    """Zip audio files per group"""
    LOGGER.info('zip audio')
    if cache.add('zip-task', '', settings.ZIP_TASK_LOCK_EXPIRATION):
        LOGGER.info('Lock acquired for zip task')
        if (settings.ZIP_AUDIO_FILES or force_zip) and not settings.USE_S3_STORAGE_FOR_AUDIO:
            zipped_files = []
            observations = Observation.objects.filter(audio_zipped=False).exclude(payload='')
            non_zipped_ids = observations.order_by('pk').values_list('pk', flat=True)
            if non_zipped_ids:
                group = get_observation_zip_group(non_zipped_ids[0])
            for observation_id in non_zipped_ids:
                if group == get_observation_zip_group(observation_id):
                    process_audio(observation_id, force_zip)
                    zipped_files.append(observation_id)
                else:
                    LOGGER.info('Processed Files: %s', zipped_files)
                    cache.delete('zip-task')
                    return
            LOGGER.info('Processed Files: %s', zipped_files)
    cache.delete('zip-task')


def get_groups_for_archiving_audio_zip_files():
    """ Returns the groups of audio files that haven't been archived yet"""
    observation_ids = Observation.objects.filter(
        audio_zipped=True, archived=False
    ).values_list(
        'pk', flat=True
    )
    return {get_observation_zip_group(pk) for pk in observation_ids}


@shared_task
def archive_audio_zip_files(force_archive=False):  # pylint: disable=R0915
    """Archive audio zip files to archive.org"""
    LOGGER.info('archive audio')
    if cache.add('archive-task', '', settings.ARCHIVE_TASK_LOCK_EXPIRATION):
        LOGGER.info('Lock acquired for archive task')
        if (settings.ARCHIVE_ZIP_FILES or force_archive) and not settings.USE_S3_STORAGE_FOR_AUDIO:
            archived_groups = []
            skipped_groups = []
            archive_skip_time = now() - timedelta(hours=settings.ARCHIVE_SKIP_TIME)
            groups = get_groups_for_archiving_audio_zip_files()
            for group in groups:
                group_range, zip_path = get_zip_range_and_path(group)
                cache_key = '{0}-{1}-{2}'.format('ziplock', group_range[0], group_range[1])
                if (not cache.add(cache_key, '', settings.ARCHIVE_ZIP_LOCK_EXPIRATION)) or (
                        not zipfile.is_zipfile(zip_path)
                ) or Observation.objects.filter(Q(end__gte=archive_skip_time) | Q(archived=True)
                                                | (Q(audio_zipped=False) & ~Q(payload=''))).filter(
                                                    pk__range=group_range).exists():
                    skipped_groups.append(group_range)
                    cache.delete(cache_key)
                    continue

                archived_groups.append(group_range)
                site = Site.objects.get_current()
                license_url = 'http://creativecommons.org/licenses/by-sa/4.0/'

                item_group = group // settings.ZIP_FILES_PER_ITEM
                files_per_item = settings.ZIP_FILES_PER_ITEM * settings.AUDIO_FILES_PER_ZIP
                item_from = (item_group * files_per_item) + 1
                item_to = (item_group + 1) * files_per_item
                item_range = '{0}-{1}'.format(str(item_from).zfill(9), str(item_to).zfill(9))

                item_id = '{0}-{1}'.format(settings.ITEM_IDENTIFIER_PREFIX, item_range)
                title = '{0} {1}'.format(settings.ITEM_TITLE_PREFIX, item_range)
                description = (
                    '<p>Audio files from <a href="{0}/observations">'
                    'SatNOGS Observations</a> with ID from {1} to {2}.</p>'
                ).format(site.domain, item_from, item_to)

                item_metadata = {
                    'collection': settings.ARCHIVE_COLLECTION,
                    'title': title,
                    'mediatype': settings.ARCHIVE_MEDIA_TYPE,
                    'licenseurl': license_url,
                    'description': description
                }

                zip_name = zip_path.split('/')[-1]
                file_metadata = {
                    'name': zip_path,
                    'title': zip_name.replace('.zip', ''),
                    'license_url': license_url,
                }

                try:
                    res = upload(
                        item_id,
                        files=file_metadata,
                        metadata=item_metadata,
                        access_key=settings.S3_ACCESS_KEY,
                        secret_key=settings.S3_SECRET_KEY,
                        retries=settings.S3_RETRIES_ON_SLOW_DOWN,
                        retries_sleep=settings.S3_RETRIES_SLEEP
                    )
                except (requests.exceptions.RequestException, AuthenticationError) as error:
                    LOGGER.info('Upload of zip %s failed, reason:\n%s', zip_name, repr(error))
                    continue

                if res[0].status_code == 200:
                    observations = Observation.objects.select_for_update().filter(
                        pk__range=group_range
                    ).filter(audio_zipped=True)
                    with transaction.atomic():
                        for observation in observations:
                            audio_filename = ''
                            audio_filename = observation.payload.name.split('/')[-1]
                            observation.archived = True
                            observation.archive_url = '{0}{1}/{2}/{3}'.format(
                                settings.ARCHIVE_URL, item_id, zip_name, audio_filename
                            )
                            observation.archive_identifier = item_id
                            if settings.REMOVE_ARCHIVED_AUDIO_FILES:
                                if observation.payload:
                                    observation.payload.delete(save=False)
                            observation.save(
                                update_fields=[
                                    'archived', 'archive_url', 'archive_identifier', 'payload'
                                ]
                            )
                    if settings.REMOVE_ARCHIVED_ZIP_FILE:
                        os.remove(zip_path)
                cache.delete(cache_key)
            cache.delete('archive-task')
            LOGGER.info('Archived Groups: %s', archived_groups)
            LOGGER.info('Skipped Groups: %s', skipped_groups)


@shared_task
def update_future_observations_with_new_tle_sets():
    """ Update future observations with latest TLE sets"""
    start = now() + timedelta(minutes=10)
    future_observations = Observation.objects.filter(start__gt=start)
    sat_id_set = set(future_observations.values_list('sat_id', flat=True))
    try:
        if sat_id_set:
            tle_sets = get_tle_sets_by_sat_id_set(sat_id_set)
        else:
            return
    except DBConnectionError:
        return
    for sat_id in sat_id_set:
        if not tle_sets[sat_id]:
            continue
        tle_set = tle_sets[sat_id][0]
        tle_updated = datetime.strptime(tle_set['updated'], "%Y-%m-%dT%H:%M:%S.%f%z")
        obs_to_update = future_observations.filter(sat_id=sat_id, tle_updated__lt=tle_updated)
        for obs in obs_to_update:
            obs.tle_line_0 = tle_set['tle0']
            obs.tle_line_1 = tle_set['tle1']
            obs.tle_line_2 = tle_set['tle2']
            obs.tle_source = tle_set['tle_source']
            obs.tle_updated = tle_set['updated']
        Observation.objects.bulk_update(
            obs_to_update, ['tle_line_0', 'tle_line_1', 'tle_line_2', 'tle_source', 'tle_updated']
        )


@shared_task
def update_future_observations_with_new_transmitter_details():
    """ Update future observations with latest Transmitter details"""
    start = now() + timedelta(minutes=10)
    future_observations = Observation.objects.select_related('ground_station').filter(
        start__gt=start
    )
    uuid_set = set(future_observations.values_list('transmitter_uuid', flat=True))

    try:
        if uuid_set:
            transmitters_set = get_transmitters_by_uuid_set(uuid_set, raise_error=False)
        else:
            return
    except DBConnectionError:
        return

    for uuid in transmitters_set.keys():
        transmitter = transmitters_set[uuid]
        transmitter_updated = datetime.strptime(transmitter['updated'], "%Y-%m-%dT%H:%M:%S.%f%z")

        checked_stations = {}
        obs_to_update = future_observations.filter(
            transmitter_uuid=uuid, transmitter_created__lt=transmitter_updated
        )
        for obs in obs_to_update:
            freq_supported = checked_stations.get(obs.ground_station.id)
            if freq_supported is None:
                freq_supported = is_transmitter_in_station_range(
                    transmitter, obs.ground_station, center_frequency=obs.center_frequency
                )
                checked_stations[obs.ground_station.id] = freq_supported
            if freq_supported:
                obs.transmitter_description = transmitter['description']
                obs.transmitter_type = transmitter['type']
                obs.transmitter_uplink_low = transmitter['uplink_low']
                obs.transmitter_uplink_high = transmitter['uplink_high']
                obs.transmitter_uplink_drift = transmitter['uplink_drift']
                obs.transmitter_downlink_low = transmitter['downlink_low']
                obs.transmitter_downlink_high = transmitter['downlink_high']
                obs.transmitter_downlink_drift = transmitter['downlink_drift']
                obs.transmitter_mode = transmitter['mode']
                obs.transmitter_invert = transmitter['invert']
                obs.transmitter_baud = transmitter['baud']
                obs.transmitter_created = transmitter['updated']
        Observation.objects.bulk_update(
            obs_to_update, [
                'transmitter_description',
                'transmitter_type',
                'transmitter_uplink_low',
                'transmitter_uplink_high',
                'transmitter_uplink_drift',
                'transmitter_downlink_low',
                'transmitter_downlink_high',
                'transmitter_downlink_drift',
                'transmitter_mode',
                'transmitter_invert',
                'transmitter_baud',
                'transmitter_created',
            ]
        )


@shared_task
def calculate_satellite_statistics():
    """Calculates statistics for each satellite based on its transmitters stats and caches them"""
    all_transmitters = (
        cache.get('transmitters-with-stats') or get_and_refresh_transmitters_with_stats_cache()
    ).values()

    satellite_stats = {}
    for transmitter in all_transmitters:
        if not satellite_stats.get(transmitter['sat_id']):
            satellite_stats[transmitter['sat_id']] = {
                'unknown_rate': 0,
                'future_rate': 0,
                'success_rate': 0,
                'bad_rate': 0,
                'total_count': 0,
                'unknown_count': 0,
                'future_count': 0,
                'good_count': 0,
                'bad_count': 0,
            }
        satellite_stats[transmitter['sat_id']
                        ]['total_count'] += transmitter['stats']['total_count']
        satellite_stats[transmitter['sat_id']
                        ]['unknown_count'] += transmitter['stats']['unknown_count']
        satellite_stats[transmitter['sat_id']
                        ]['future_count'] += transmitter['stats']['future_count']
        satellite_stats[transmitter['sat_id']]['good_count'] += transmitter['stats']['good_count']
        satellite_stats[transmitter['sat_id']]['bad_count'] += transmitter['stats']['bad_count']

    del all_transmitters

    for sat in satellite_stats.values():
        total_count = sat['total_count']
        if total_count:
            sat['unknown_rate'] = math.trunc(10000 * (sat['unknown_count'] / total_count)) / 100
            sat['future_rate'] = math.trunc(10000 * (sat['future_count'] / total_count)) / 100
            sat['success_rate'] = math.trunc(10000 * (sat['good_count'] / total_count)) / 100
            sat['bad_rate'] = math.trunc(10000 * (sat['bad_count'] / total_count)) / 100

    cache.set('satellite_stats', satellite_stats)
    return satellite_stats


@shared_task
def fetch_satellites():
    """Fetch all satellites from SatNOGS DB and stores them in cache

       Throws: requests.exceptions.ConectionError"""

    db_api_url = settings.DB_API_ENDPOINT
    if not db_api_url:
        LOGGER.info("Zero length api url, fetching is stopped")
        raise DBConnectionError('Error in DB API connection. Blank DB API URL!')
    satellites_url = "{}satellites".format(db_api_url)

    LOGGER.info("Fetching Satellites from %s", satellites_url)
    try:
        r_satellites = requests.get(satellites_url, timeout=settings.DB_API_TIMEOUT)
    except requests.exceptions.RequestException as error:
        raise DBConnectionError('Error in DB API connection. Please try again!') from error
    satellite_dict = {}
    for satellite in r_satellites.json():
        sat_id = satellite.get('sat_id')
        satellite_dict[sat_id] = satellite
        for associated_sat_id in satellite['associated_satellites']:
            satellite_dict[associated_sat_id] = copy.deepcopy(satellite)
            satellite_dict[associated_sat_id]['merged_into'] = satellite['sat_id']

    cache.set('satellites', satellite_dict)
    calculate_satellite_statistics.delay()
    return satellite_dict


@shared_task
def clean_observations():
    """Task to clean up old observations that lack actual data."""
    threshold = now() - timedelta(days=int(settings.OBSERVATION_OLD_RANGE))
    observations = Observation.objects.filter(end__lt=threshold, archived=False) \
                                      .exclude(payload='')
    for obs in observations:
        if settings.ENVIRONMENT == 'stage':
            if not obs.status >= 100:
                obs.delete()
                continue


@shared_task
def sync_to_db():
    """Task to send all non-synced demod data to SatNOGS DB / SiDS"""
    frames = DemodData.objects.filter(
        copied_to_db=False, is_image=False
    ).exclude(observation__transmitter_mode__in=settings.NOT_SYNCED_MODES).filter(
        observation__station_lng__isnull=False, observation__station_lat__isnull=False
    )
    sats = cache.get('satellites') or fetch_satellites()
    for frame in frames:
        try:
            sync_demoddata_to_db(frame, sats[frame.observation.sat_id])
        except requests.exceptions.RequestException:
            continue


@shared_task
def sync_frame_to_db(frame_id):
    """Task to send a single demod data to SatNOGS DB / SiDS"""
    frame = DemodData.objects.select_related("observation").get(pk=frame_id)
    sats = cache.get('satellites') or fetch_satellites()
    missing_station_coord = not bool(
        frame.observation.station_lat and frame.observation.station_lng
    )
    mode_in_nonsynced = bool(frame.observation.transmitter_mode in settings.NOT_SYNCED_MODES)
    if any((frame.is_image, missing_station_coord, mode_in_nonsynced)):
        pass
    try:
        sync_demoddata_to_db(frame, sats[frame.observation.sat_id])
    except requests.exceptions.RequestException:
        pass


@shared_task
def station_status_update():
    """Task to update Station status."""
    post_save.disconnect(_station_post_save, sender=Station)
    for station in Station.objects.all():
        station.update_status(created=False)
    post_save.connect(_station_post_save, sender=Station, weak=False)


@shared_task
def notify_for_stations_without_results():
    """Task to send email for stations with observations without results."""
    email_to = settings.EMAIL_FOR_STATIONS_ISSUES
    if email_to:
        stations = ''
        obs_limit = settings.OBS_NO_RESULTS_MIN_COUNT
        time_limit = now() - timedelta(seconds=settings.OBS_NO_RESULTS_IGNORE_TIME)
        last_check = time_limit - timedelta(seconds=settings.OBS_NO_RESULTS_CHECK_PERIOD)
        for station in Station.objects.filter(status=2):
            last_obs = Observation.objects.filter(
                ground_station=station, end__lt=time_limit
            ).order_by("-end")[:obs_limit]
            obs_without_results = 0
            obs_after_last_check = False
            for observation in last_obs:
                if not (observation.has_audio and observation.has_waterfall):
                    obs_without_results += 1
                if observation.end >= last_check:
                    obs_after_last_check = True
            if obs_without_results == obs_limit and obs_after_last_check:
                stations += f'{station.id}\n'
        if stations:
            # Notify user
            subject = '[satnogs] Station with observations without results'
            send_mail(
                subject, stations, settings.DEFAULT_FROM_EMAIL,
                [settings.EMAIL_FOR_STATIONS_ISSUES], False
            )
