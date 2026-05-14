"""helpers for scheduling functions in network.base.scheduling."""
import math
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.utils.timezone import now

DEFAULT_DURATION = {
    "split": 300,
    "break": 60,
}


def make_tle():
    """
    Return a reusable mock TLE dictionary for scheduling tests.

    The values are intentionally static because orbital accuracy is not
    relevant for unit-level scheduling branch coverage.
    """
    return {
        "tle0": "ISS (ZARYA)",
        "tle1": ("1 25544U 98067A   23001.00000000  .00000000 "
                 "00000-0  00000-0 0  9999"),
        "tle2": ("2 25544  51.6400   0.0000 0000000 "
                 "0.0000   0.0000 15.50000000000000"),
    }


def make_station(
    lng=0.0,
    lat=0.0,
    alt=10,
    horizon=0,
    horizon_hard_limit=False,
    min_culmination=0,
    min_culmination_hard_limit=False,
    scheduled_obs=None,
):
    """
    Return a mock station object configured for scheduling tests.

    The helper centralizes station configuration and allows tests to
    override only the parameters relevant to the current scenario.
    """
    station = MagicMock()
    station.lng = lng
    station.lat = lat
    station.alt = alt
    station.horizon = horizon
    station.horizon_hard_limit = horizon_hard_limit
    station.min_culmination = min_culmination
    station.min_culmination_hard_limit = min_culmination_hard_limit
    station.scheduled_obs = scheduled_obs or []
    return station


def make_pass(
    rise,
    set_,
    rise_az=10.0,
    set_az=20.0,
    tca_alt=45.0,
):
    """
    Return a mock pass dictionary compatible with scheduling functions.

    The structure matches the dictionaries returned by next_pass()
    and GEO/overhead observation generators.
    """
    return {
        "rise_time": rise,
        "set_time": set_,
        "tca_time": rise + ((set_ - rise) / 2),
        "rise_az": rise_az,
        "set_az": set_az,
        "tca_alt": tca_alt,
    }


def make_time_window(duration_seconds):
    """
    Return a deterministic rise/set datetime pair for scheduling tests.

    Microseconds are removed to avoid precision mismatches in assertions.
    """
    rise = now().replace(microsecond=0)
    set_ = rise + timedelta(seconds=duration_seconds)
    return rise, set_


def make_observer():
    """
    Return a generic observer mock suitable for scheduling tests.
    """
    return MagicMock()


def make_satellite(altitude=0, azimuth=0, copy_return=None):
    """
    Return a configurable mock satellite for scheduling tests.

    The altitude value can be adjusted to simulate below-horizon,
    overhead, or GEO scheduling scenarios.
    """
    satellite = MagicMock()
    satellite.alt = altitude
    satellite.az = azimuth

    satellite.copy.return_value = copy_return or MagicMock()

    return satellite


def attach_satellite_sample_map(satellite_copy, sample_map, visited=None):
    """Attach a side effect to satellite_copy.compute() that updates az/alt
    based on the provided sample_map."""

    def side_effect(obs):
        """Update satellite_copy.az and satellite_copy.alt based on obs.date."""
        if visited is not None:
            visited.append(obs.date)

        az, alt = sample_map[obs.date]
        satellite_copy.az = math.radians(az)
        satellite_copy.alt = math.radians(alt)

    satellite_copy.compute.side_effect = side_effect


def make_scheduled_observation(start, end):
    """
    Return a scheduled observation namespace object.

    The object mimics the structure expected by overlap detection logic.
    """
    return SimpleNamespace(start=start, end=end)
