"""Tests for generate_overhead_observation_window function in network.base.scheduling."""
# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
import math
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import ephem
import pytest

from network.base import scheduling
from network.base.scheduling import generate_overhead_observation_window
from network.base.test_scheduling import attach_altitude_sequence, patched_now
from network.base.tests import StationFactory


class TestGenerateOverheadObservationWindowUnitBugsExposed:
    """Unit tests that expose actual bugs in the function implementation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mocks for observer and satellite."""
        self.observer = MagicMock(spec=ephem.Observer)
        self.observer.horizon = ephem.degrees('5')
        self.observer.date = ephem.Date(datetime(2023, 1, 1, 12, 0, 0))

        self.satellite = MagicMock(spec=ephem.EarthSatellite)
        self.satellite.az = 1.57
        yield

    def test_exposes_datetime_string_comparison_bug(self):
        """Expose the datetime < string comparison bug."""
        attach_altitude_sequence(self.satellite, [0.2, 0.1, -0.1])

        with patched_now(datetime(2023, 1, 1, 11, 0, 0)):
            # Function should either fix the comparison or this test documents the bug
            with pytest.raises(TypeError, match="'<' not supported"):
                generate_overhead_observation_window(self.observer, self.satellite)

    def test_search_stops_after_24_hours_when_satellite_never_sets(self):
        """Test that search loop enforces strict 24-hour limit."""
        self.observer.date = ephem.Date(datetime(2023, 1, 1, 12, 0, 0))
        self.observer.horizon = ephem.degrees('-10')

        attach_altitude_sequence(self.satellite, [0.2])

        with patched_now(datetime(2023, 1, 1, 11, 0, 0)):
            # Will fail on datetime < str comparison after loop completes
            with pytest.raises(TypeError):
                generate_overhead_observation_window(self.observer, self.satellite)

        # Verify loop ran exactly to 24-hour limit
        assert self.satellite.compute.call_count == 1441

    def test_initial_compute_controls_whether_loop_executes(self):
        """Verify that initial compute() is called and controls loop execution."""
        original_date = self.observer.date

        def compute_side_effect(_obs):  # pylint: disable=unused-argument
            # Always below horizon
            self.satellite.alt = -0.1

        self.satellite.compute.side_effect = compute_side_effect

        with patch('network.base.scheduling.now') as mock_now:
            mock_now.return_value = datetime(2023, 1, 1, 11, 0, 0)

            with pytest.raises(TypeError):
                generate_overhead_observation_window(self.observer, self.satellite)

        # Only initial compute, no loop iterations
        assert self.satellite.compute.call_count == 1
        # If satellite stays below horizon, date is not advanced in loop
        assert self.observer.date == original_date


class TestGenerateOverheadObservationWindowBehaviorDesired:
    """Tests that describe DESIRED behavior.

    These tests will FAIL with current implementation due to bugs.
    They document what the function SHOULD do.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mocks for observer and satellite."""
        self.observer = MagicMock(spec=ephem.Observer)
        self.observer.horizon = '5'
        self.observer.date = ephem.Date(datetime(2023, 1, 1, 12, 0, 0))

        self.satellite = MagicMock(spec=ephem.EarthSatellite)
        self.satellite.az = 1.57
        yield

    @pytest.mark.xfail(
        reason="Function has datetime < str bug",
        raises=TypeError,
        strict=True,
    )
    def test_should_return_dict_with_required_keys(self):
        """Function SHOULD return dict with all six required keys."""
        attach_altitude_sequence(self.satellite, [0.2, 0.25, 0.2, 0.15, 0.05, -0.1])

        with patched_now(datetime(2023, 1, 1, 11, 0, 0)):
            result = generate_overhead_observation_window(self.observer, self.satellite)

        assert result
        expected_keys = {
            'rise_time',
            'rise_az',
            'set_time',
            'set_az',
            'tca_time',
            'tca_alt',
        }
        assert set(result.keys()) == expected_keys
        assert isinstance(result['rise_time'], datetime)
        assert isinstance(result['set_time'], datetime)
        assert isinstance(result['tca_time'], datetime)
        assert isinstance(result['rise_az'], int)
        assert isinstance(result['tca_alt'], int)
        assert isinstance(result['set_az'], int)

    @pytest.mark.xfail(
        reason="Function has datetime < str bug",
        raises=TypeError,
        strict=True,
    )
    def test_should_return_empty_dict_for_short_duration(self):
        """Function SHOULD return {} when pass duration is below minimum."""
        attach_altitude_sequence(self.satellite, [0.2, -0.1])

        with patched_now(datetime(2023, 1, 1, 11, 0, 0)):
            result = generate_overhead_observation_window(self.observer, self.satellite)

        assert not result

    @pytest.mark.xfail(
        reason="Function has datetime < str bug AND max_alt = satellite.az bug",
        strict=True,
    )
    def test_should_detect_peak_altitude_correctly(self):
        """Function SHOULD detect peak altitude."""
        # If we fix both bugs, this test will validate real peak detection
        attach_altitude_sequence(self.satellite, [0.2, 0.3, 0.4, 0.35, 0.2, 0.1, -0.05])

        with patched_now(datetime(2023, 1, 1, 11, 0, 0)):
            result = generate_overhead_observation_window(self.observer, self.satellite)

        # 0.4 radians * 180/π ≈ 23 degrees
        assert result['tca_alt'] == 23

    @pytest.mark.xfail(
        reason="Function has datetime < str bug AND does not restore observer.date",
        strict=True,
    )
    def test_should_restore_observer_date_to_original_value(self):
        """Function SHOULD restore observer.date, but currently it doesn't."""
        original_date = ephem.Date(datetime(2023, 1, 1, 10, 0, 0))
        self.observer.date = original_date

        attach_altitude_sequence(self.satellite, [0.2, 0.25, 0.2, 0.15, 0.05, -0.1])

        with patched_now(datetime(2023, 1, 1, 11, 0, 0)):
            generate_overhead_observation_window(self.observer, self.satellite)

        assert self.observer.date == original_date


@pytest.mark.django_db
class TestGenerateOverheadObservationWindowIntegrationRobust:
    """Integration tests with real pyephem objects.

    These tests MUST fail loudly if conditions aren't met.
    No conditional assertions that allow silent passing.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup with real station and mock satellite."""
        self.station = StationFactory(name="Test Station", lng=-8.0, lat=38.7, alt=150, horizon=5)

        # Create a mock satellite that behaves like a real ephem.EarthSatellite
        # This avoids TLE checksum validation issues while maintaining integration
        # with real Observer
        self.satellite = MagicMock(spec=ephem.EarthSatellite)
        self.satellite.az = 1.57
        self.satellite.alt = 0.5
        yield

    def _find_overhead_time(
        self,
        observer,
        satellite,
        start_date,
        search_minutes=1440,
    ):
        """Helper: Find a time when satellite is overhead.

        Args:
            observer: ephem.Observer
            satellite: ephem.EarthSatellite
            start_date: date to start search (string format for ephem.Date)
            search_minutes: max minutes to search forward

        Returns:
            ephem.Date when satellite is overhead.

        Raises:
            AssertionError if no overhead time found within search_minutes.
        """
        observer.date = ephem.Date(start_date)

        for _ in range(search_minutes):
            satellite.compute(observer)

            # Convert satellite altitude from radians to degrees explicitly
            altitude_deg = float(satellite.alt) * 180 / math.pi
            if altitude_deg > float(observer.horizon):
                return ephem.Date(observer.date)

            observer.date = ephem.Date(observer.date + ephem.minute)

        raise AssertionError(
            f"No overhead pass found within {search_minutes} minutes "
            f"starting from {start_date}"
        )

    def test_function_raises_type_error_due_to_datetime_string_comparison(self):
        """Integration test: Confirms the datetime < str bug exists."""
        observer = ephem.Observer()
        observer.lon = str(self.station.lng)
        observer.lat = str(self.station.lat)
        observer.elevation = self.station.alt
        observer.pressure = 0
        observer.horizon = str(self.station.horizon)

        # Find a time when satellite is definitely overhead
        overhead_date = self._find_overhead_time(
            observer,
            self.satellite,
            '2023/1/15 00:00:00',
        )

        observer.date = overhead_date

        # Function MUST raise TypeError due to datetime < str comparison bug
        with pytest.raises(TypeError, match="'<' not supported"):
            generate_overhead_observation_window(observer, self.satellite)

    def test_altitude_range_at_overhead_time_is_reasonable(self):
        """Test: When satellite is overhead, altitude should be significantly above."""
        observer = ephem.Observer()
        observer.lon = str(self.station.lng)
        observer.lat = str(self.station.lat)
        observer.elevation = self.station.alt
        observer.pressure = 0
        observer.horizon = str(self.station.horizon)

        overhead_date = self._find_overhead_time(
            observer,
            self.satellite,
            '2023/1/15 00:00:00',
        )
        observer.date = overhead_date

        self.satellite.compute(observer)
        altitude_deg = float(self.satellite.alt) * 180 / math.pi

        # At overhead time, altitude must be above horizon (5 degrees)
        assert altitude_deg > float(
            observer.horizon
        ), (f"Altitude {altitude_deg}° should be > horizon {observer.horizon}°")

        # Altitude should be reasonable (between horizon and zenith)
        assert 0 <= altitude_deg <= 90, (f"Altitude should be 0-90°, got {altitude_deg}°")

    def test_observer_state_consistency_through_compute_calls(self):
        """Test: Observer object maintains consistent state during computations."""
        observer = ephem.Observer()
        observer.lon = str(self.station.lng)
        observer.lat = str(self.station.lat)
        observer.elevation = self.station.alt
        observer.pressure = 0
        observer.horizon = str(self.station.horizon)

        overhead_date = self._find_overhead_time(
            observer,
            self.satellite,
            '2023/1/15 00:00:00',
        )

        original_lon = observer.lon
        original_lat = observer.lat
        original_elevation = observer.elevation

        observer.date = overhead_date

        try:
            with pytest.raises(TypeError):
                generate_overhead_observation_window(observer, self.satellite)
        finally:
            # Observer geographic properties should not change
            # (even if date was modified during execution)
            assert observer.lon == original_lon
            assert observer.lat == original_lat
            assert observer.elevation == original_elevation


class TestGenerateObservationWindowBugIsolation:
    """Additional focused tests that isolate bugs."""

    class _ComparableDateTime(datetime):
        """DateTime subclass that allows comparison with strings for testing."""

        @classmethod
        def from_datetime(cls, value):
            """Create from a datetime object."""
            return cls(
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
                value.microsecond,
                tzinfo=value.tzinfo,
            )

        def __lt__(self, other):
            """Override less-than to handle string comparison."""
            if isinstance(other, str):
                return False
            return super().__lt__(other)

    class _FakeEphemDate:
        """Fake ephem.Date for testing."""

        def __init__(self, value):
            """Initialize with a datetime value."""
            self._value = value

        def __add__(self, other):
            """Handle addition with ephem.minute."""
            if other == ephem.minute:
                new_value = self._value + timedelta(minutes=1)
            else:
                new_value = self._value + other
            return TestGenerateObservationWindowBugIsolation._FakeEphemDate(new_value)

        def datetime(self):
            """Return comparable datetime."""
            return TestGenerateObservationWindowBugIsolation._ComparableDateTime.\
                from_datetime(self._value)

        def __eq__(self, other):
            """Handle equality comparison."""
            if isinstance(other, TestGenerateObservationWindowBugIsolation._FakeEphemDate):
                return self._value == other._value
            return self._value == other

        def __repr__(self):
            """String representation."""
            return repr(self._value)

    def _fake_ephem_date(self, value):
        """Convert value to FakeEphemDate."""
        if isinstance(value, self._FakeEphemDate):
            return value
        if isinstance(value, datetime):
            return self._FakeEphemDate(value)
        if hasattr(value, 'datetime'):
            return self._FakeEphemDate(value.datetime())
        return value

    def _build_isolated_observer_and_satellite(self, altitude_map, az_initial=3.0):
        """Build isolated observer and satellite for testing."""
        observer = MagicMock(spec=ephem.Observer)
        observer.horizon = '5'
        start_dt = datetime(2023, 1, 1, 12, 0, 0)
        observer.date = self._FakeEphemDate(start_dt)

        satellite = MagicMock(spec=ephem.EarthSatellite)

        def compute_side_effect(current_observer):
            """Compute side effect."""
            current_dt = current_observer.date.datetime()
            minute_index = int((current_dt - start_dt).total_seconds() // 60)
            altitude, azimuth = altitude_map.get(
                minute_index,
                altitude_map[max(altitude_map)],
            )
            satellite.alt = altitude
            satellite.az = azimuth if minute_index == 0 else azimuth

        satellite.compute.side_effect = compute_side_effect
        satellite.az = az_initial
        return observer, satellite, start_dt

    @pytest.mark.xfail(
        reason="Documents the max_alt initialization bug while running the real function",
        strict=False
    )
    def test_max_alt_bug_shows_wrong_initial_comparison_basis(self):
        """Show that initializing max_alt from az hides the true altitude peak."""
        altitude_map = {
            0: (0.10, 3.00),
            1: (0.20, 3.00),
            2: (0.40, 3.00),
            3: (0.35, 3.00),
            4: (0.10, 3.00),
            5: (-0.10, 3.00),
        }
        observer, satellite, _ = self._build_isolated_observer_and_satellite(altitude_map)

        with patch(
                'network.base.scheduling.ephem.Date',
                side_effect=self._fake_ephem_date,
        ), patch('network.base.scheduling.now') as mock_now:
            mock_now.return_value = datetime(2023, 1, 1, 11, 0, 0)
            result = scheduling.generate_overhead_observation_window(observer, satellite)

        # Correct behavior would pick the 0.40 rad peak (~23 degrees).
        assert result['tca_alt'] == 23
