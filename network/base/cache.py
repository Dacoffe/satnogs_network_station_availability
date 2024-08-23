"""Utility functions to get data from the cache"""
from django.core.cache import cache

from network.base.tasks import calculate_satellite_statistics, fetch_satellites


def get_satellites() -> dict:
    """Returns the satellites either from cache or from DB."""
    return cache.get('satellites') or fetch_satellites()


def get_satellite_by_norad(norad: int) -> dict | None:
    """Returns the satellite with the given norad id"""
    assert isinstance(norad, int)
    sats = get_satellites()
    for sat in sats.values():
        if sat['norad_cat_id'] == norad:
            return sat
    return None


def get_satellite_stats():
    """Returns satellite stats, either just calculated or from cache."""
    return cache.get('satellite_stats') or calculate_satellite_statistics()
