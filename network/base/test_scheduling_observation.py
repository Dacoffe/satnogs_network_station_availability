"""Comprehensive Tests for create_new_observation() Function"""
# pylint: disable=redefined-outer-name,unused-argument,too-few-public-methods
import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils.timezone import now

from network.base import scheduling
from network.base.models import Antenna, AntennaType, FrequencyRange, Observation, Station
from network.base.scheduling import create_new_observation
from network.base.validators import NegativeElevationError, NoTleSetError, \
    ObservationOverlapError, OutOfRangeError
from network.users.models import User


@pytest.fixture
def transmitter_data():
    """Sample transmitter data dict"""
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
        }
    }


@pytest.fixture
def satellite_tle():
    """Sample TLE data - realistic format"""
    return {
        'tle0': 'ISS (ZARYA)',
        'tle1': '1 25544U 98067A   24001.00000000  .00016717  00000-0  29762-3 0  9005',
        'tle2': '2 25544  51.6416 339.8014 0006812 130.5360 325.0288 15.54179074 20',
        'tle_source': 'celestrak',
        'updated': now(),
    }


@pytest.fixture
def station(db):
    """Create a test station"""
    return Station.objects.create(
        name='Test Station',
        lng=10.0,
        lat=40.0,
        alt=100,
        horizon=10,
        min_culmination=10,
        testing=False,
    )


@pytest.fixture
def antenna_with_frequencies(db, station):
    """Create antenna with 145-146 MHz frequency range"""
    antenna_type, _ = AntennaType.objects.get_or_create(name='Dipole')
    antenna = Antenna.objects.create(
        station=station,
        antenna_type=antenna_type,
    )
    FrequencyRange.objects.create(
        antenna=antenna,
        min_frequency=145000000,
        max_frequency=146000000,
    )
    return antenna


@pytest.fixture
def future_window():
    """Create observation window 1 day from now, 10 minutes duration"""
    start = now() + timedelta(days=1)
    end = start + timedelta(minutes=10)
    return start, end


@pytest.fixture
def valid_orbital_mocks(monkeypatch, transmitter_data, future_window, satellite_tle):
    """Mock ALL orbital and external operations for deterministic testing.

    Returns a dict of all mocks that can be overridden in individual tests.
    This ensures tests pass/fail for logical reasons, not orbital mechanics luck.

    Includes a fake Observer class to isolate from real PyEphem.
    """
    _, end = future_window

    class FakeObserver:
        """Minimal fake Observer to track assignments"""

        def __init__(self):
            self.lon = None
            self.lat = None
            self.elevation = None
            self.date = None
            self.pressure = None
            self.horizon = None

    get_satellites_mock = Mock(
        return_value={
            transmitter_data['sat_id']: {
                'sat_id': transmitter_data['sat_id'],
            },
        }
    )

    get_tle_set_mock = Mock(return_value=[satellite_tle])

    readtle_mock = Mock(return_value=object())

    observer_mock = Mock(side_effect=FakeObserver)

    # Returns: (start_azimuth, end_azimuth, max_altitude)
    recalculate_window_mock = Mock(return_value=(11.0, 222.0, 55.0))

    # Called twice: start and end. Both positive = success.
    get_altitude_mock = Mock(side_effect=[10.0, 12.0])

    # Next pass much later = observation doesn't span multiple passes
    next_pass_mock = Mock(return_value={'rise_time': end + timedelta(hours=1)})

    monkeypatch.setattr(scheduling, 'get_satellites', get_satellites_mock)
    monkeypatch.setattr(scheduling, 'get_tle_set_by_sat_id', get_tle_set_mock)
    monkeypatch.setattr(scheduling.ephem, 'readtle', readtle_mock)
    monkeypatch.setattr(scheduling.ephem, 'Observer', observer_mock)
    monkeypatch.setattr(scheduling, 'recalculate_window_parameters', recalculate_window_mock)
    monkeypatch.setattr(scheduling, 'get_altitude', get_altitude_mock)
    monkeypatch.setattr(scheduling, 'next_pass', next_pass_mock)

    return {
        'get_satellites': get_satellites_mock,
        'get_tle_set_by_sat_id': get_tle_set_mock,
        'readtle': readtle_mock,
        'Observer': observer_mock,
        'recalculate_window_parameters': recalculate_window_mock,
        'get_altitude': get_altitude_mock,
        'next_pass': next_pass_mock,
    }


@pytest.fixture
def user(db):
    """Create a test user"""
    return User.objects.create_user(username="testuser", password="pass")


class TestCreateNewObservationSuccess:
    """Test successful observation creation with all fields properly filled"""

    @pytest.mark.django_db
    def test_successful_creation_returns_unsaved_observation(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that successful creation returns an Observation with all fields filled"""
        start, end = future_window

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        # Verify NOT saved to DB
        assert obs.pk is None

        # Verify core fields
        assert obs.author == user
        assert obs.ground_station == station
        assert obs.start == start
        assert obs.end == end
        assert obs.sat_id == transmitter_data['sat_id']

        # Verify transmitter fields are copied
        assert obs.transmitter_uuid == transmitter_data['uuid']
        assert obs.transmitter_description == transmitter_data['description']
        assert obs.transmitter_type == transmitter_data['type']
        assert obs.transmitter_mode == transmitter_data['mode']
        assert obs.transmitter_invert == transmitter_data['invert']
        assert obs.transmitter_baud == transmitter_data['baud']
        assert obs.transmitter_uplink_low == transmitter_data['uplink_low']
        assert obs.transmitter_uplink_high == transmitter_data['uplink_high']
        assert obs.transmitter_downlink_low == transmitter_data['downlink_low']
        assert obs.transmitter_downlink_high == transmitter_data['downlink_high']
        assert obs.transmitter_uplink_drift == transmitter_data['uplink_drift']
        assert obs.transmitter_downlink_drift == transmitter_data['downlink_drift']

        # Verify TLE fields
        assert obs.tle_line_0 == satellite_tle['tle0']
        assert obs.tle_line_1 == satellite_tle['tle1']
        assert obs.tle_line_2 == satellite_tle['tle2']
        assert obs.tle_source == satellite_tle['tle_source']
        assert obs.tle_updated == satellite_tle['updated']

        # Verify orbital parameters from mocks
        assert obs.rise_azimuth == 11.0
        assert obs.set_azimuth == 222.0
        assert obs.max_altitude == 55.0

        # Verify station data is copied
        assert obs.station_alt == station.alt
        assert obs.station_lat == station.lat
        assert obs.station_lng == station.lng
        assert obs.experimental == station.testing

        # Verify frequency and status
        assert obs.center_frequency == 145900000
        assert obs.transmitter_status is True
        assert obs.transmitter_unconfirmed == transmitter_data['unconfirmed']
        assert obs.transmitter_parameters == transmitter_data['params']

        # Verify mocks were called appropriately
        valid_orbital_mocks['readtle'].assert_called_once_with(
            str(satellite_tle['tle0']),
            str(satellite_tle['tle1']),
            str(satellite_tle['tle2']),
        )

        # Verify get_altitude was called with start and end times
        altitude_calls = valid_orbital_mocks['get_altitude'].call_args_list
        assert len(altitude_calls) == 2
        assert altitude_calls[0].args[2] == start
        assert altitude_calls[1].args[2] == end

        valid_orbital_mocks['recalculate_window_parameters'].assert_called_once()
        valid_orbital_mocks['next_pass'].assert_called_once()

    @pytest.mark.django_db
    def test_antenna_data_serialized_to_json(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that antenna data is correctly serialized to JSON"""
        start, end = future_window

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        antennas = json.loads(obs.station_antennas)

        assert isinstance(antennas, list)
        assert len(antennas) == 1
        assert antennas[0]['type'] == 'Dipole'
        assert len(antennas[0]['ranges']) == 1
        assert antennas[0]['ranges'][0]['min'] == 145000000
        assert antennas[0]['ranges'][0]['max'] == 146000000

    @pytest.mark.django_db
    def test_with_provided_tle_set_skips_fetch(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that when tle_set is provided, get_tle_set_by_sat_id is NOT called"""
        start, end = future_window

        create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        # Should NOT call the fetch function
        valid_orbital_mocks['get_tle_set_by_sat_id'].assert_not_called()

    @pytest.mark.django_db
    def test_without_provided_tle_set_calls_fetch(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that when tle_set is NOT provided, get_tle_set_by_sat_id IS called"""
        start, end = future_window

        create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=None,
        )

        # Should call the fetch function
        valid_orbital_mocks['get_tle_set_by_sat_id'].assert_called_once_with(
            transmitter_data['sat_id']
        )


class TestCreateNewObservationEarlyExit:
    """Test error cases that should exit before making external calls"""

    @pytest.mark.django_db
    def test_overlap_check_raises_before_external_calls(
        self,
        station,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        monkeypatch,
    ):
        """Test that Overlap check raises BEFORE calling get_satellites"""
        start, end = future_window

        # Create existing overlapping observation with all required fields
        Observation.objects.create(
            sat_id=transmitter_data['sat_id'],
            ground_station=station,
            author=user,
            start=start - timedelta(minutes=5),
            end=start + timedelta(minutes=5),
            tle_line_0=satellite_tle['tle0'],
            tle_line_1=satellite_tle['tle1'],
            tle_line_2=satellite_tle['tle2'],
            transmitter_uuid=transmitter_data['uuid'],
            transmitter_description=transmitter_data['description'],
            transmitter_type=transmitter_data['type'],
            transmitter_uplink_low=transmitter_data['uplink_low'],
            transmitter_uplink_high=transmitter_data['uplink_high'],
            transmitter_uplink_drift=transmitter_data['uplink_drift'],
            transmitter_downlink_low=transmitter_data['downlink_low'],
            transmitter_downlink_high=transmitter_data['downlink_high'],
            transmitter_downlink_drift=transmitter_data['downlink_drift'],
            transmitter_mode=transmitter_data['mode'],
            transmitter_invert=transmitter_data['invert'],
            transmitter_baud=transmitter_data['baud'],
            transmitter_created=transmitter_data['updated'],
            transmitter_status=True,
            transmitter_unconfirmed=transmitter_data['unconfirmed'],
            transmitter_parameters=transmitter_data['params'],
            station_alt=station.alt,
            station_lat=station.lat,
            station_lng=station.lng,
            station_antennas='[]',
            rise_azimuth=0,
            set_azimuth=0,
            max_altitude=0,
        )

        get_satellites_mock = Mock()
        monkeypatch.setattr(scheduling, 'get_satellites', get_satellites_mock)

        with pytest.raises(ObservationOverlapError) as exc_info:
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
            )

        # Verify external call was NOT made (early exit)
        get_satellites_mock.assert_not_called()

        # Verify error message is informative
        assert "overlap" in str(exc_info.value).lower()
        assert str(station.id) in str(exc_info.value)


class TestCreateNewObservationNoTleSet:
    """Test error when TLE set is missing or empty"""

    @pytest.mark.django_db
    def test_missing_tle_set_raises_no_tle_error(
        self,
        station,
        transmitter_data,
        user,
        future_window,
        monkeypatch,
    ):
        """Test that empty TLE response raises NoTleSetError"""
        start, end = future_window

        monkeypatch.setattr(
            scheduling,
            'get_satellites',
            Mock(
                return_value={
                    transmitter_data['sat_id']: {
                        'sat_id': transmitter_data['sat_id'],
                    },
                }
            ),
        )
        monkeypatch.setattr(
            scheduling,
            'get_tle_set_by_sat_id',
            Mock(return_value=[]),
        )

        with pytest.raises(NoTleSetError):
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
            )

    @pytest.mark.django_db
    def test_db_connection_error_on_tle_fetch_raises_no_tle_error(
        self,
        station,
        transmitter_data,
        user,
        future_window,
        monkeypatch,
    ):
        """Test that DB error during TLE fetch results in NoTleSetError"""
        start, end = future_window

        monkeypatch.setattr(
            scheduling,
            'get_satellites',
            Mock(
                return_value={
                    transmitter_data['sat_id']: {
                        'sat_id': transmitter_data['sat_id'],
                    },
                }
            ),
        )
        monkeypatch.setattr(
            scheduling,
            'get_tle_set_by_sat_id',
            Mock(side_effect=scheduling.DBConnectionError("Connection failed")),
        )

        with pytest.raises(NoTleSetError):
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
            )


class TestCreateNewObservationElevation:
    """Test elevation validation errors"""

    @pytest.mark.django_db
    def test_negative_elevation_at_start_raises_error(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that negative elevation at start time raises NegativeElevationError"""
        start, end = future_window

        # Mock get_altitude to return negative at start, positive at end
        valid_orbital_mocks['get_altitude'].side_effect = [-0.1, 10.0]

        with pytest.raises(NegativeElevationError) as exc_info:
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
                center_frequency=145900000,
                tle_set=[satellite_tle],
            )

        assert "start datetime" in str(exc_info.value)
        assert transmitter_data['uuid'] in str(exc_info.value)

        # Verify next_pass was NOT called (early exit)
        valid_orbital_mocks['next_pass'].assert_not_called()

    @pytest.mark.django_db
    def test_negative_elevation_at_end_raises_error(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that negative elevation at end time raises NegativeElevationError"""
        start, end = future_window

        # Mock get_altitude to return positive at start, negative at end
        valid_orbital_mocks['get_altitude'].side_effect = [10.0, -0.1]

        with pytest.raises(NegativeElevationError) as exc_info:
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
                center_frequency=145900000,
                tle_set=[satellite_tle],
            )

        assert "end datetime" in str(exc_info.value)
        assert transmitter_data['uuid'] in str(exc_info.value)

        # Verify next_pass was NOT called (early exit)
        valid_orbital_mocks['next_pass'].assert_not_called()

    @pytest.mark.django_db
    def test_zero_elevation_at_start_is_allowed(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that elevation of exactly 0 at start is accepted"""
        start, end = future_window

        valid_orbital_mocks['get_altitude'].side_effect = [0.0, 10.0]

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        assert obs.start == start

    @pytest.mark.django_db
    def test_zero_elevation_at_end_is_allowed(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that elevation of exactly 0 at end is accepted"""
        start, end = future_window

        valid_orbital_mocks['get_altitude'].side_effect = [10.0, 0.0]

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        assert obs.end == end


class TestCreateNewObservationFrequency:
    """Test center frequency validation"""

    @pytest.mark.django_db
    def test_frequency_out_of_range_raises_error(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that center frequency outside antenna range raises OutOfRangeError"""
        start, end = future_window

        with pytest.raises(OutOfRangeError):
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
                center_frequency=144000000,
                tle_set=[satellite_tle],
            )

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "center_frequency,should_succeed", [
            (145000000, True),
            (145500000, True),
            (146000000, True),
            (144999999, False),
            (146000001, False),
        ]
    )
    def test_frequency_boundary_validation(
        self,
        center_frequency,
        should_succeed,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test frequency validation at boundaries"""
        start, end = future_window

        if should_succeed:
            obs = create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
                center_frequency=center_frequency,
                tle_set=[satellite_tle],
            )
            assert obs.center_frequency == center_frequency
        else:
            with pytest.raises(OutOfRangeError):
                create_new_observation(
                    station=station,
                    transmitter=transmitter_data,
                    start=start,
                    end=end,
                    author=user,
                    center_frequency=center_frequency,
                    tle_set=[satellite_tle],
                )

    @pytest.mark.django_db
    def test_no_center_frequency_provided_succeeds(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that center_frequency=None is accepted"""
        start, end = future_window

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=None,
            tle_set=[satellite_tle],
        )

        assert obs.center_frequency is None

    @pytest.mark.django_db
    def test_zero_center_frequency_is_stored_as_none(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that center_frequency=0 is treated as None (falsy value)"""
        start, end = future_window

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=0,
            tle_set=[satellite_tle],
        )

        assert obs.center_frequency is None

    @pytest.mark.django_db
    def test_station_without_antennas_accepts_no_center_frequency(
        self,
        station,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that station without antennas accepts None center_frequency"""
        start, end = future_window

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=None,
            tle_set=[satellite_tle],
        )

        antennas = json.loads(obs.station_antennas)
        assert antennas == []
        assert obs.center_frequency is None

    @pytest.mark.django_db
    def test_station_without_antennas_rejects_center_frequency(
        self,
        station,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that station without antennas rejects any center_frequency"""
        start, end = future_window

        with pytest.raises(OutOfRangeError):
            create_new_observation(
                station=station,
                transmitter=transmitter_data,
                start=start,
                end=end,
                author=user,
                center_frequency=145900000,
                tle_set=[satellite_tle],
            )


class TestCreateNewObservationTransmitterStatus:
    """Test transmitter status field mapping"""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "status,expected", [
            ('active', True),
            ('inactive', False),
            ('disabled', False),
            ('testing', False),
        ]
    )
    def test_transmitter_status_mapping(
        self,
        status,
        expected,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that transmitter status is correctly mapped to boolean"""
        start, end = future_window
        transmitter_data['status'] = status

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        assert obs.transmitter_status is expected


class TestCreateNewObservationMultipleAntennas:
    """Test serialization of multiple antennas and ranges"""

    @pytest.mark.django_db
    def test_multiple_antennas_and_ranges_are_serialized(
        self,
        station,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that multiple antennas with multiple ranges are all serialized"""
        antenna_type_uhf, _ = AntennaType.objects.get_or_create(name='UHF')
        antenna_type_vhf, _ = AntennaType.objects.get_or_create(name='VHF')

        uhf = Antenna.objects.create(station=station, antenna_type=antenna_type_uhf)
        vhf = Antenna.objects.create(station=station, antenna_type=antenna_type_vhf)

        FrequencyRange.objects.create(
            antenna=uhf,
            min_frequency=435000000,
            max_frequency=438000000,
        )
        FrequencyRange.objects.create(
            antenna=uhf,
            min_frequency=2400000000,
            max_frequency=2450000000,
        )

        FrequencyRange.objects.create(
            antenna=vhf,
            min_frequency=145000000,
            max_frequency=146000000,
        )

        start, end = future_window

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        antennas = json.loads(obs.station_antennas)

        assert len(antennas) == 2

        by_type = {antenna['type']: antenna['ranges'] for antenna in antennas}

        uhf_ranges = sorted(
            by_type['UHF'],
            key=lambda item: (item['min'], item['max']),
        )
        vhf_ranges = sorted(
            by_type['VHF'],
            key=lambda item: (item['min'], item['max']),
        )

        assert uhf_ranges == [
            {
                'min': 435000000,
                'max': 438000000
            },
            {
                'min': 2400000000,
                'max': 2450000000
            },
        ]
        assert vhf_ranges == [
            {
                'min': 145000000,
                'max': 146000000
            },
        ]


class TestCreateNewObservationTransmitterStatusEdgeCases:
    """Test transmitter status field edge cases"""

    @pytest.mark.django_db
    def test_transmitter_status_is_case_sensitive(
        self,
        station,
        antenna_with_frequencies,
        transmitter_data,
        user,
        future_window,
        satellite_tle,
        valid_orbital_mocks,
    ):
        """Test that transmitter status comparison is case-sensitive"""
        start, end = future_window
        transmitter_data['status'] = 'Active'  # Uppercase

        obs = create_new_observation(
            station=station,
            transmitter=transmitter_data,
            start=start,
            end=end,
            author=user,
            center_frequency=145900000,
            tle_set=[satellite_tle],
        )

        assert obs.transmitter_status is False
