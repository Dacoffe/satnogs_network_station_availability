"""Module for calculating and keep in cache satellite and transmitter statistics"""
import math

from django.core.cache import cache
from django.utils.timezone import now

from network.base.models import Observation
from network.base.tasks import get_and_refresh_transmitters_with_stats_cache


def get_transmitter_with_stats_by_uuid(uuid):
    """Given a UUID, it returns the transmitter with its statistics"""

    all_transmitters = cache.get('transmitters-with-stats'
                                 ) or get_and_refresh_transmitters_with_stats_cache()
    return all_transmitters.get(uuid)


def get_satellite_stats_by_transmitter_list(transmitter_list):
    """Calculate satellite statistics based on the statistics of its transmitters"""
    total_count = 0
    unknown_count = 0
    future_count = 0
    good_count = 0
    bad_count = 0
    unknown_rate = 0
    future_rate = 0
    success_rate = 0
    bad_rate = 0

    transmitters_with_stats = get_transmitters_with_stats(transmitter_list)

    for transmitter in transmitters_with_stats:
        total_count += transmitter['total_count']
        unknown_count += transmitter['unknown_count']
        future_count += transmitter['future_count']
        good_count += transmitter['good_count']
        bad_count += transmitter['bad_count']

    if total_count:
        unknown_rate = math.trunc(10000 * (unknown_count / total_count)) / 100
        future_rate = math.trunc(10000 * (future_count / total_count)) / 100
        success_rate = math.trunc(10000 * (good_count / total_count)) / 100
        bad_rate = math.trunc(10000 * (bad_count / total_count)) / 100

    return {
        'total_count': total_count,
        'unknown_count': unknown_count,
        'future_count': future_count,
        'good_count': good_count,
        'bad_count': bad_count,
        'unknown_rate': unknown_rate,
        'future_rate': future_rate,
        'success_rate': success_rate,
        'bad_rate': bad_rate
    }


def get_transmitters_with_stats(transmitters_list):
    """
    Given a list of transmitter objects as they are returned from DB's API,
    the statistics for each transmitter are added to the object
    """
    all_transmitters = cache.get('transmitters-with-stats'
                                 ) or get_and_refresh_transmitters_with_stats_cache()
    transmitters_with_stats_list = []
    unknown_stats = {
        'total_count': 0,
        'unknown_count': 0,
        'future_count': 0,
        'good_count': 0,
        'bad_count': 0,
        'unknown_rate': 0,
        'future_rate': 0,
        'success_rate': 0,
        'bad_rate': 0
    }
    for transmitter in transmitters_list:
        cached_transmitter = all_transmitters.get(transmitter['uuid'])
        stats = cached_transmitter['stats'] if cached_transmitter else unknown_stats
        transmitters_with_stats_list.append(dict(transmitter, **stats))

    return transmitters_with_stats_list


def unknown_observations_count(user):
    """Returns a count of unknown status observations per user"""
    user_unknown_count = cache.get('user-{0}-unknown-count'.format(user.id))
    if user_unknown_count is None:
        user_unknown_count = Observation.objects.filter(
            author=user, status__range=(0, 99), end__lte=now()
        ).exclude(
            waterfall_old='', waterfall=''
        ).count()
        cache.set('user-{0}-unknown-count'.format(user.id), user_unknown_count, 120)

    return user_unknown_count
