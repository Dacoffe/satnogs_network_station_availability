"""Helpers and fixtures for scheduling functions in network.base.scheduling."""
# pylint: disable=redefined-outer-name,unused-argument
import math
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils.timezone import now

from network.base.models import Antenna, AntennaType, FrequencyRange, Station
from network.users.models import User

DEFAULT_DURATION = {
    "split": 300,
    "break": 60,
}


def make_tle():
    """Return a reusable mock TLE dictionary for scheduling tests."""
    return {
        "tle0": "ISS (ZARYA)",
        "tle1": ("1 25544U 98067A   23001.00000000  .00000000 "
                 "00000-0  00000-0 0  9999"),
        "tle2": ("2 25544  51.6400   0.0000 0000000 "
                 "0.0000   0.0000 15.50000000000000"),
    }


def make_transmitter_data():
    """Return a reusable transmitter payload for scheduling tests.

    The values are intentionally static because these tests focus on
    observation assembly rather than transmitter lookup logic.
    """
    return {
        'sat_id': 25544,
        'uuid': 'test-uuid-12345',
        'norad_cat_id': 25544,
        'description': 'ISS Test Transmitter',
        'type': 'Transponder',
        'uplink_low': 145000000,
        'uplink_high': 145800000,
        'uplink_drift': 0,
        'downlink_low': 145800000,
        'downlink_high': 146000000,
        'downlink_drift': 0,
        'mode': 'FM',
        'invert': False,
        'baud': 9600,
        'updated': now(),
        'status': 'active',
        'unconfirmed': False,
        'params': {
            'key': 'value'
        },
    }


def make_satellite_tle():
    """Return a reusable realistic satellite TLE payload for tests."""
    return {
        'tle0': 'ISS (ZARYA)',
        'tle1': '1 25544U 98067A   24001.00000000  .00016717  00000-0  29762-3 0  9005',
        'tle2': '2 25544  51.6416 339.8014 0006812 130.5360 325.0288 15.54179074 20',
        'tle_source': 'celestrak',
        'updated': now(),
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
    """Return a mock station object configured for scheduling tests.

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


def make_db_station(
    name='Test Station',
    lng=10.0,
    lat=40.0,
    alt=100,
    horizon=10,
    min_culmination=10,
    testing=False,
):
    """Return a persisted Station object for integration-style scheduling tests."""
    return Station.objects.create(
        name=name,
        lng=lng,
        lat=lat,
        alt=alt,
        horizon=horizon,
        min_culmination=min_culmination,
        testing=testing,
    )


def make_antenna_with_frequencies(
    station,
    antenna_type_name='Dipole',
    min_frequency=145000000,
    max_frequency=146000000,
):
    """Return an antenna with a single frequency range attached."""
    antenna_type, _ = AntennaType.objects.get_or_create(name=antenna_type_name)
    antenna = Antenna.objects.create(station=station, antenna_type=antenna_type)
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=min_frequency,
        max_frequency=max_frequency,
    )
    return antenna


def make_pass(
    rise,
    set_,
    rise_az=10.0,
    set_az=20.0,
    tca_alt=45.0,
):
    """Return a mock pass dictionary compatible with scheduling functions.

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
    """Return a deterministic rise/set datetime pair for scheduling tests.

    Microseconds are removed to avoid precision mismatches in assertions.
    """
    rise = now().replace(microsecond=0)
    set_ = rise + timedelta(seconds=duration_seconds)
    return rise, set_


def make_observer():
    """Return a generic observer mock suitable for scheduling tests."""
    return MagicMock()


def make_satellite(altitude=0, azimuth=0, copy_return=None):
    """Return a configurable mock satellite for scheduling tests.

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


def attach_altitude_sequence(satellite, altitudes):
    """Attach a sequence of altitude values to satellite.compute() calls."""
    call_count = [0]

    def compute_side_effect(_obs):
        """Update satellite altitude from sequence."""
        satellite.alt = altitudes[min(call_count[0], len(altitudes) - 1)]
        call_count[0] += 1

    satellite.compute.side_effect = compute_side_effect


@contextmanager
def patched_now(dt):
    """Context manager to mock network.base.scheduling.now."""
    with patch('network.base.scheduling.now') as mock_now:
        mock_now.return_value = dt
        yield mock_now


def make_scheduled_observation(start, end):
    """Return a scheduled observation namespace object."""
    return SimpleNamespace(start=start, end=end)


def add_frequency_range_to_station(
    station,
    *,
    antenna_type_name='Test Antenna',
    min_frequency=145000000,
    max_frequency=146000000,
):
    """Helper to create antenna with frequency range on a station."""
    antenna_type, _ = AntennaType.objects.get_or_create(name=antenna_type_name)
    antenna = Antenna.objects.create(
        station=station,
        antenna_type=antenna_type,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=min_frequency,
        max_frequency=max_frequency,
    )
    return antenna


# ============================================================================
# FIXTURES FOR test_scheduling_available.py
# ============================================================================


@pytest.fixture
def user(db):
    """Create a test user for scheduling tests."""
    return User.objects.create_user(username="testuser", password="pass")


@pytest.fixture
def station_basic(db):
    """Create a basic test station."""
    return Station.objects.create(
        name='Basic Station',
        lng=10.0,
        lat=40.0,
        alt=100,
        horizon=10,
        min_culmination=10,
        testing=False,
        violator_scheduling=2,
    )


@pytest.fixture
def station_violator_restricted(db):
    """Create station with violator_scheduling=0 (no violators allowed)."""
    return Station.objects.create(
        name='Violator Restricted Station',
        lng=15.0,
        lat=45.0,
        alt=150,
        horizon=10,
        min_culmination=10,
        testing=False,
        violator_scheduling=0,
    )


@pytest.fixture
def station_violator_special_perm(db):
    """Create station with violator_scheduling=1 (special permission required)."""
    return Station.objects.create(
        name='Violator Special Perm Station',
        lng=20.0,
        lat=50.0,
        alt=200,
        horizon=10,
        min_culmination=10,
        testing=False,
        violator_scheduling=1,
    )


@pytest.fixture
def antenna_vhf(db, station_basic):
    """Create VHF antenna on basic station with 145-146 MHz range."""
    antenna_type, _ = AntennaType.objects.get_or_create(name='VHF Dipole')
    antenna = Antenna.objects.create(
        station=station_basic,
        antenna_type=antenna_type,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=145000000,
        max_frequency=146000000,
    )
    return antenna


@pytest.fixture
def antenna_uhf(db, station_basic):
    """Create UHF antenna on basic station with 435-438 MHz range."""
    antenna_type, _ = AntennaType.objects.get_or_create(name='UHF Yagi')
    antenna = Antenna.objects.create(
        station=station_basic,
        antenna_type=antenna_type,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=435000000,
        max_frequency=438000000,
    )
    return antenna


@pytest.fixture
def station_with_multiple_frequency_ranges(db):
    """Create station with antenna having multiple non-overlapping frequency ranges."""
    station = Station.objects.create(
        name='Multi-Range Station',
        lng=5.0,
        lat=35.0,
        alt=50,
        horizon=10,
        min_culmination=10,
        testing=False,
        violator_scheduling=2,
    )
    antenna_type, _ = AntennaType.objects.get_or_create(name='Multi-Band')
    antenna = Antenna.objects.create(
        station=station,
        antenna_type=antenna_type,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=145000000,
        max_frequency=146000000,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=435000000,
        max_frequency=438000000,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=2400000000,
        max_frequency=2450000000,
    )
    return station


@pytest.fixture
def station_no_antennas(db):
    """Create station without any antennas."""
    return Station.objects.create(
        name='No Antennas Station',
        lng=25.0,
        lat=55.0,
        alt=250,
        horizon=10,
        min_culmination=10,
        testing=False,
        violator_scheduling=2,
    )
