"""SatNOGS Network scheduling functions"""
# ephem is missing lon, lat, elevation and horizon attributes in Observer class slots,
# Disable assigning-non-slot pylint error:
# pylint: disable=E0237
import json
import math
from datetime import timedelta

import ephem
from django.conf import settings
from django.utils.timezone import make_aware, now, utc

from network.base.db_api import DBConnectionError, get_tle_set_by_norad_id
from network.base.models import Observation, Satellite
from network.base.perms import schedule_stations_perms
from network.base.utils import format_frequency
from network.base.validators import NegativeElevationError, NoTleSetError, \
    ObservationOverlapError, OutOfRangeError, SinglePassError


def get_altitude(observer, satellite, date):
    """Returns altitude of satellite in a specific date for a specific observer"""
    observer = observer.copy()
    satellite = satellite.copy()
    observer.date = date
    satellite.compute(observer)
    return float(format(math.degrees(satellite.alt), '.0f'))


def get_azimuth(observer, satellite, date):
    """Returns azimuth of satellite in a specific date for a specific observer"""
    observer = observer.copy()
    satellite = satellite.copy()
    observer.date = date
    satellite.compute(observer)
    return float(format(math.degrees(satellite.az), '.0f'))


def over_min_duration(duration):
    """Returns if duration is equal or greater than the minimum one set in settings"""
    return duration >= settings.OBSERVATION_DURATION_MIN


def recalculate_window_parameters(observer, satellite, window_start, window_end):
    """Finds the maximum altitude of a satellite during a certain observation window"""
    observer = observer.copy()
    satellite = satellite.copy()
    observer.date = window_end
    satellite.compute(observer)
    end_azimuth = float(format(math.degrees(satellite.az), '.0f'))
    observer.date = window_start
    satellite.compute(observer)
    start_azimuth = float(format(math.degrees(satellite.az), '.0f'))

    interval = 1  # in seconds
    max_altitude = 0
    date = window_start
    while date < window_end:
        observer.date = date
        satellite.compute(observer)
        altitude = float(format(math.degrees(satellite.alt), '.0f'))
        max_altitude = max(altitude, max_altitude)
        date = date + timedelta(seconds=interval)

    return (start_azimuth, end_azimuth, max_altitude)


def split_long_window(start, end, duration, split_duration, break_duration):
    """
    Split long passes into 'split_duration' seconds ones and let between them a period of
    'break_duration' seconds
    """
    windows = []
    split_number = (int(duration) // (split_duration + break_duration)) + 1
    total_splits = split_number

    last_split_duration = duration % (split_duration + break_duration)
    if not over_min_duration(last_split_duration):
        total_splits -= 1

    for split in range(0, total_splits):
        start_offset = split * (split_duration + break_duration)
        window_start = start + timedelta(seconds=start_offset)
        if total_splits - split == 1:  # last split
            window_end = end
        else:
            window_end = window_start + timedelta(seconds=split_duration)
        windows.append({'start': window_start, 'end': window_end})

    return windows


def resolve_overlaps(scheduled_obs, start, end):
    """
    This function checks for overlaps between all existing observations on `scheduled_obs`
    and a potential new observation with given `start` and `end` time.

    Returns
    - ([], True)                                  if total overlap exists
    - ([(start1, end1), (start2, end2)], True)    if the overlap happens in the middle
                                                  of the new observation
    - ([(start, end)], True)                      if the overlap happens at one end
                                                  of the new observation
    - ([(start, end)], False)                     if no overlap exists
    """
    overlapped = False
    if scheduled_obs:
        for datum in scheduled_obs:
            if datum.start <= end and start <= datum.end:
                overlapped = True
                if datum.start <= start and datum.end >= end:
                    return ([], True)
                if start < datum.start and end > datum.end:
                    # In case of splitting the window  to two we
                    # check for overlaps for each generated window.
                    window1 = resolve_overlaps(
                        scheduled_obs, start, datum.start - timedelta(seconds=30)
                    )
                    window2 = resolve_overlaps(
                        scheduled_obs, datum.end + timedelta(seconds=30), end
                    )
                    return (window1[0] + window2[0], True)
                if datum.start <= start:
                    start = datum.end + timedelta(seconds=30)
                if datum.end >= end:
                    end = datum.start - timedelta(seconds=30)
    return ([(start, end)], overlapped)


def create_station_window(
    window_start,
    window_end,
    azr,
    azs,
    altitude,
    tle,
    valid_duration,
    overlapped,
    split,
    overlap_ratio=0
):
    """Creates an observation window"""
    return {
        'start': window_start.strftime("%Y-%m-%d %H:%M:%S.%f"),
        'end': window_end.strftime("%Y-%m-%d %H:%M:%S.%f"),
        'az_start': azr,
        'az_end': azs,
        'elev_max': altitude,
        'tle0': tle['tle0'],
        'tle1': tle['tle1'],
        'tle2': tle['tle2'],
        'valid_duration': valid_duration,
        'overlapped': overlapped,
        'split': split,
        'overlap_ratio': overlap_ratio
    }


def create_station_windows(
    scheduled_obs, overlapped, pass_params, observer, satellite, tle, duration
):
    """
    This function takes a pre-calculated pass (described by pass_params) over a certain station
    and a list of already scheduled observations, and calculates observation windows during which
    the station is available to observe the pass.

    Returns the list of all available observation windows
    """
    station_windows = []

    if not duration:
        duration = {
            'split': settings.OBSERVATION_SPLIT_DURATION,
            'break': settings.OBSERVATION_SPLIT_BREAK_DURATION
        }
    windows, windows_changed = resolve_overlaps(
        scheduled_obs, pass_params['rise_time'], pass_params['set_time']
    )

    if not windows:
        # No overlapping windows found
        return []
    if windows_changed:
        # Windows changed due to overlap, recalculate observation parameters
        if overlapped == 0:
            return []

        if overlapped == 1:
            initial_duration = (pass_params['set_time'] - pass_params['rise_time']).total_seconds()
            for window_start, window_end in windows:
                window_duration = (window_end - window_start).total_seconds()
                if not over_min_duration(window_duration):
                    continue

                if window_duration > duration['split']:
                    split_windows = split_long_window(
                        window_start, window_end, window_duration, duration['split'],
                        duration['break']
                    )
                    for split_window in split_windows:
                        # Add windows for a partial split passes
                        start_azimuth, end_azimuth, max_altitude = recalculate_window_parameters(
                            observer, satellite, split_window['start'], split_window['end']
                        )
                        station_windows.append(
                            create_station_window(
                                split_window['start'], split_window['end'], start_azimuth,
                                end_azimuth, max_altitude, tle, True, True, True,
                                min(1, 1 - (window_duration / initial_duration))
                            )
                        )
                else:
                    # Add a window for a partial pass
                    start_azimuth, end_azimuth, max_altitude = recalculate_window_parameters(
                        observer, satellite, window_start, window_end
                    )
                    station_windows.append(
                        create_station_window(
                            window_start, window_end, start_azimuth, end_azimuth,
                            max_altitude, tle, True, True, False,
                            min(1, 1 - (window_duration / initial_duration))
                        )
                    )
        elif overlapped == 2:
            initial_duration = (pass_params['set_time'] - pass_params['rise_time']).total_seconds()
            total_window_duration = 0
            window_duration = 0
            duration_validity = False
            for window_start, window_end in windows:
                window_duration = (window_end - window_start).total_seconds()
                duration_validity = duration_validity or over_min_duration(window_duration)
                total_window_duration += window_duration

            # If duration is longer than 12min then satellite is probably on higher than LEO orbit
            # and we need to recalculate pass parameters
            if initial_duration > 720:
                start_azimuth, end_azimuth, max_altitude = recalculate_window_parameters(
                    observer, satellite, pass_params['rise_time'], pass_params['set_time']
                )
            else:
                start_azimuth, end_azimuth, max_altitude = (
                    pass_params['rise_az'], pass_params['set_az'], pass_params['tca_alt']
                )
            # Add a window for the overlapped pass, this is for station page and will not be split
            # as we want it as one. The split will be done when user click on schedule button for
            # this observation and it will be moved to observation/new page.
            station_windows.append(
                create_station_window(
                    pass_params['rise_time'], pass_params['set_time'], start_azimuth, end_azimuth,
                    max_altitude, tle, duration_validity, True, False,
                    min(1, 1 - (total_window_duration / initial_duration))
                )
            )
    else:
        window_duration = (windows[0][1] - windows[0][0]).total_seconds()
        if over_min_duration(window_duration):
            # if overlapped == 2 then the pass is presented in station page, in this case pass
            # should be kept without splitting
            if window_duration > duration['split'] and overlapped != 2:
                split_windows = split_long_window(
                    windows[0][0], windows[0][1], window_duration, duration['split'],
                    duration['break']
                )
                for split_window in split_windows:
                    # Add windows for a partial split passes
                    start_azimuth, end_azimuth, max_altitude = recalculate_window_parameters(
                        observer, satellite, split_window['start'], split_window['end']
                    )
                    station_windows.append(
                        create_station_window(
                            split_window['start'], split_window['end'], start_azimuth, end_azimuth,
                            max_altitude, tle, True, False, True, 0
                        )
                    )
            else:
                # If duration is longer than 12min then satellite is probably on higher than LEO
                # orbit and we need to recalculate pass parameters
                if window_duration > 720:
                    start_azimuth, end_azimuth, max_altitude = recalculate_window_parameters(
                        observer, satellite, pass_params['rise_time'], pass_params['set_time']
                    )
                else:
                    start_azimuth, end_azimuth, max_altitude = (
                        pass_params['rise_az'], pass_params['set_az'], pass_params['tca_alt']
                    )
                # Add a window for a full pass
                station_windows.append(
                    create_station_window(
                        pass_params['rise_time'], pass_params['set_time'], start_azimuth,
                        end_azimuth, max_altitude, tle, True, False, False, 0
                    )
                )
    return station_windows


def next_pass(observer, satellite, singlepass=True):
    """Returns the next pass of the satellite above the observer"""
    rise_time, rise_az, tca_time, tca_alt, set_time, set_az = observer.next_pass(
        satellite, singlepass
    )
    # Convert output of pyephems.next_pass into processible values
    pass_start = make_aware(ephem.Date(rise_time).datetime(), utc)
    pass_end = make_aware(ephem.Date(set_time).datetime(), utc)
    pass_tca = make_aware(ephem.Date(tca_time).datetime(), utc)
    pass_azr = float(format(math.degrees(rise_az), '.0f'))
    pass_azs = float(format(math.degrees(set_az), '.0f'))
    pass_altitude = float(format(math.degrees(tca_alt), '.0f'))

    return {
        'rise_time': pass_start,
        'set_time': pass_end,
        'tca_time': pass_tca,
        'rise_az': pass_azr,
        'set_az': pass_azs,
        'tca_alt': pass_altitude
    }


def generate_geo_observation_window(observer, satellite, start, end):
    '''Calculate a pass for an object already overhead

    :param observer: ephem object for the station
    :type observer: ephem.Observer
    :param satellite: ephem object for the satellite
    :type satellite: ephem.Body
    :param start: Start datetime of scheduling period
    :type start: datetime string in '%Y-%m-%d %H:%M'
    :param end: End datetime of scheduling period
    :type end: datetime string in '%Y-%m-%d %H:%M'

    :return: pass parameters used for generating observation windows
    '''
    pass_params = {}
    satellite.compute(observer)
    pass_params['rise_time'] = start
    pass_params['rise_az'] = int(satellite.az * 180 / math.pi)
    pass_params['tca_time'] = (start + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S.%f")
    pass_params['tca_alt'] = int(satellite.alt * 180 / math.pi)
    # skip to end of period and take 'set' measurements
    observer.date = ephem.Date(observer.date + 24 * ephem.hour)
    satellite.compute(observer)
    pass_params['set_time'] = end
    pass_params['set_az'] = int(satellite.az * 180 / math.pi)
    return pass_params


def generate_overhead_observation_window(observer, satellite):
    '''Calculate a pass for an object already overhead

    :param observer: ephem object for the station
    :type observer: ephem.Observer
    :param satellite: ephem object for the satellite
    :type satellite: ephem.Body

    :return: pass parameters used for generating observation windows
    '''
    pass_params = {}
    min_horizon = float(observer.horizon)
    satellite.compute(observer)
    # Window is up, rise time is now
    pass_params['rise_time'] = observer.date.datetime()
    pass_params['rise_az'] = int(satellite.az * 180 / math.pi)
    max_alt = satellite.az
    max_alt_time = observer.date
    minutes_for_finding_rise = 0
    # Search forward to set time, and catch tca during search
    while ephem.degrees(satellite.alt) > min_horizon and \
            minutes_for_finding_rise < 60 * 24:
        if max_alt < satellite.alt:
            max_alt = satellite.alt
            max_alt_time = observer.date
        minutes_for_finding_rise += 1
        observer.date = ephem.Date(observer.date + ephem.minute)
        satellite.compute(observer)
    observation_min_end = (
        now() + timedelta(minutes=settings.OBSERVATION_DATE_MIN_START) +
        timedelta(seconds=settings.OBSERVATION_DURATION_MIN)
    ).strftime("%Y-%m-%d %H:%M:%S.%f")
    if observer.date.datetime() < observation_min_end:
        return {}
    # Found set time
    pass_params['set_time'] = observer.date.datetime()
    pass_params['set_az'] = int(satellite.az * 180 / math.pi)
    # Move to TCA
    observer.date = max_alt_time
    satellite.compute(observer)
    pass_params['tca_time'] = observer.date.datetime()
    pass_params['tca_alt'] = int(satellite.alt * 180 / math.pi)
    return pass_params


def predict_available_observation_windows(
    station, min_horizon, overlapped, tle, start, end, duration
):
    '''Calculate available observation windows for a certain station and satellite during
    the given time period.

    :param station: Station for scheduling
    :type station: Station django.db.model.Model
    :param min_horizon: Overwrite station minimum horizon if defined
    :type min_horizon: integer or None
    :param overlapped: Calculate and return overlapped observations fully, truncated or not at all
    :type overlapped: integer values: 0 (no return), 1(truncated overlaps), 2(full overlaps)
    :param tle: Satellite current TLE
    :type tle: dictionary with Tle details
    :param start: Start datetime of scheduling period
    :type start: datetime string in '%Y-%m-%d %H:%M'
    :param end: End datetime of scheduling period
    :type end: datetime string in '%Y-%m-%d %H:%M'
    :param sat: Satellite for scheduling
    :type sat: Satellite django.db.model.Model

    :return: List of passes found and list of available observation windows
    '''
    passes_found = []
    station_windows = []
    # Initialize pyehem Satellite for propagation
    satellite = ephem.readtle(str(tle['tle0']), str(tle['tle1']), str(tle['tle2']))
    # Initialize pyephem Observer for propagation
    observer = ephem.Observer()
    observer.lon = str(station.lng)
    observer.lat = str(station.lat)
    observer.elevation = station.alt
    observer.date = ephem.Date(start)
    # Speeds up calculations by removing refraction
    observer.pressure = 0
    if min_horizon is not None:
        observer.horizon = str(min_horizon)
    else:
        observer.horizon = str(station.horizon)

    try:
        try:
            satellite.compute(observer)
        except ValueError:
            return passes_found, station_windows

        # satellite currently up
        if ephem.degrees(satellite.alt) > float(observer.horizon):
            try:
                # Will cause GEO to error out, HEO & LEO caught here
                geo_pass = False
                pass_params = next_pass(observer, satellite)
                # Discard previous results, generate window from satellite overhead
                pass_params = generate_overhead_observation_window(observer, satellite)
            # GEO caught here
            except ValueError:
                pass_params = generate_geo_observation_window(observer, satellite, start, end)
                geo_pass = True
            except TypeError:
                return passes_found, station_windows
            passes_found.append(pass_params)
            # Check if overlaps with existing scheduled observations
            # Adjust or discard window if overlaps exist
            scheduled_obs = station.scheduled_obs

            station_windows.extend(
                create_station_windows(
                    scheduled_obs, overlapped, pass_params, observer, satellite, tle, duration
                )
            )
            time_start_new = pass_params['set_time'] + timedelta(minutes=1)
            observer.date = time_start_new.strftime("%Y-%m-%d %H:%M:%S.%f")
            if geo_pass:
                return passes_found, station_windows

    except RuntimeError:
        return passes_found, station_windows

    while True:
        try:
            pass_params = next_pass(observer, satellite)
        # We catch TypeError, to avoid cases like this one that is described in ephem issue:
        # https://github.com/brandon-rhodes/pyephem/issues/176
        except (TypeError, ValueError):
            break

        # no match if the sat will not rise above the configured min horizon
        if pass_params['rise_time'] >= end:
            # start of next pass outside of window bounds
            break

        if pass_params['set_time'] > end:
            # end of next pass outside of window bounds
            pass_params['set_time'] = end

        passes_found.append(pass_params)
        # Check if overlaps with existing scheduled observations
        # Adjust or discard window if overlaps exist
        scheduled_obs = station.scheduled_obs

        station_windows.extend(
            create_station_windows(
                scheduled_obs, overlapped, pass_params, observer, satellite, tle, duration
            )
        )
        time_start_new = pass_params['set_time'] + timedelta(minutes=1)
        observer.date = time_start_new.strftime("%Y-%m-%d %H:%M:%S.%f")
    return passes_found, station_windows


def create_new_observation(
    station, transmitter, start, end, author, center_frequency=None, tle_set=None
):
    """
    Creates and returns a new Observation object

    Arguments:
    :param station: network.base.models.Station
    :param transmitter: network.base.models.Transmitter
    :param start: datetime
    :param end: datetime
    :param author: network.base.models.User
    :param tle_set: empty list or list of one tle set
    :param center_frequency

    :return network.base.models.Observation
    :raises NegativeElevationError, ObservationOverlapError, SinglePassError or more
    """
    scheduled_obs = Observation.objects.filter(ground_station=station).filter(end__gt=now())
    window = resolve_overlaps(scheduled_obs, start, end)

    if window[1]:
        raise ObservationOverlapError(
            'One or more observations of station {0} overlap with the already scheduled ones.'.
            format(station.id)
        )

    sat = Satellite.objects.get(norad_cat_id=transmitter['norad_cat_id'])
    if not tle_set:
        try:
            tle_set = get_tle_set_by_norad_id(transmitter['norad_cat_id'])
        except DBConnectionError:
            tle_set = []

        if not tle_set:
            raise NoTleSetError(
                'Satellite with transmitter {} and NORAD ID {} hasn\'t available TLE set'.format(
                    transmitter['uuid'], transmitter['norad_cat_id']
                )
            )

    tle = tle_set[0]
    sat_ephem = ephem.readtle(str(tle['tle0']), str(tle['tle1']), str(tle['tle2']))
    observer = ephem.Observer()
    observer.lon = str(station.lng)
    observer.lat = str(station.lat)
    observer.elevation = station.alt

    rise_azimuth, set_azimuth, max_altitude = recalculate_window_parameters(
        observer, sat_ephem, start, end
    )
    rise_altitude = get_altitude(observer, sat_ephem, start)
    set_altitude = get_altitude(observer, sat_ephem, end)

    if rise_altitude < 0:
        raise NegativeElevationError(
            "Satellite with transmitter {} has negative altitude ({})"
            " for station {} at start datetime: {}".format(
                transmitter['uuid'], rise_altitude, station.id, start
            )
        )
    if set_altitude < 0:
        raise NegativeElevationError(
            "Satellite with transmitter {} has negative altitude ({})"
            " for station {} at end datetime: {}".format(
                transmitter['uuid'], set_altitude, station.id, end
            )
        )
    # Using a short time (1min later) after start for finding the next pass of the satellite to
    # check that end datetime is before the start datetime of the next pass, in other words that
    # end time belongs to the same single pass.
    observer.date = start + timedelta(minutes=1)
    try:
        next_satellite_pass = next_pass(observer, sat_ephem, False)
        if next_satellite_pass['rise_time'] < end:
            raise SinglePassError(
                "Observation should include only one pass of the satellite with transmitter {}"
                " on station {}, please check start({}) and end({}) datetimes and try again".
                format(transmitter['uuid'], station.id, start, end)
            )
    # not valid for always up
    except ValueError:
        pass

    # List all station antennas with their frequency ranges.
    antennas = []
    is_center_frequency_in_station_range = False
    for antenna in station.antennas.all().prefetch_related('frequency_ranges', 'antenna_type'):
        ranges = []
        for frequency_range in antenna.frequency_ranges.all():
            if (center_frequency and frequency_range.min_frequency <= center_frequency <=
                    frequency_range.max_frequency):
                is_center_frequency_in_station_range = True

            ranges.append(
                {
                    "min": frequency_range.min_frequency,
                    "max": frequency_range.max_frequency
                }
            )
        antennas.append({"type": antenna.antenna_type.name, "ranges": ranges})

    if center_frequency and not is_center_frequency_in_station_range:
        raise OutOfRangeError(
            'Center frequency({}) is not in station {} supported frequencies'.format(
                format_frequency(center_frequency), station.id
            )
        )

    return Observation(
        satellite=sat,
        tle_line_0=tle['tle0'],
        tle_line_1=tle['tle1'],
        tle_line_2=tle['tle2'],
        tle_source=tle['tle_source'],
        tle_updated=tle['updated'],
        author=author,
        start=start,
        end=end,
        ground_station=station,
        testing=station.testing,
        rise_azimuth=rise_azimuth,
        max_altitude=max_altitude,
        set_azimuth=set_azimuth,
        transmitter_uuid=transmitter['uuid'],
        transmitter_description=transmitter['description'],
        transmitter_type=transmitter['type'],
        transmitter_uplink_low=transmitter['uplink_low'],
        transmitter_uplink_high=transmitter['uplink_high'],
        transmitter_uplink_drift=transmitter['uplink_drift'],
        transmitter_downlink_low=transmitter['downlink_low'],
        transmitter_downlink_high=transmitter['downlink_high'],
        transmitter_downlink_drift=transmitter['downlink_drift'],
        transmitter_mode=transmitter['mode'],
        transmitter_invert=transmitter['invert'],
        transmitter_baud=transmitter['baud'],
        transmitter_created=transmitter['updated'],
        station_alt=station.alt,
        station_lat=station.lat,
        station_lng=station.lng,
        station_antennas=json.dumps(antennas),
        center_frequency=center_frequency or None,
        transmitter_status=transmitter["status"] == "active",
        transmitter_unconfirmed=transmitter["unconfirmed"]
    )


def get_available_stations(stations, downlink, user, satellite):
    """Returns stations for scheduling filtered by a specific downlink and user's permissions"""
    available_stations = []

    if satellite.is_frequency_violator:
        stations = stations.exclude(violator_scheduling=0)
        if not user.groups.filter(name='Operators').exists():
            stations = stations.exclude(violator_scheduling=1)

    stations_perms = schedule_stations_perms(user, stations)
    stations_with_permissions = [station for station in stations if stations_perms[station.id]]
    for station in stations_with_permissions:
        # Skip if this station is not capable of receiving the frequency
        if not downlink:
            continue
        for gs_antenna in station.antennas.all():
            for frequency_range in gs_antenna.frequency_ranges.all():
                if frequency_range.min_frequency <= downlink <= frequency_range.max_frequency:
                    available_stations.append(station)
                    break
            else:
                continue  # to the next antenna of the station
            break  # station added to the available stations

    return available_stations
