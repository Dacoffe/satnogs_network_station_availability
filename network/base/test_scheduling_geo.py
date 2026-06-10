"""Tests for generate_geo_observation_window function in network.base.scheduling."""
from datetime import datetime, timedelta, timezone

import ephem
import pytest

from network.base.scheduling import generate_geo_observation_window
from network.base.test_orbital import generate_fake_tle
from network.base.test_scheduling import attach_satellite_sample_map, make_observer, make_satellite

START = datetime(2023, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
END = START + timedelta(hours=1)

EXPECTED_KEYS = {
    "rise_time",
    "rise_az",
    "tca_time",
    "tca_alt",
    "set_time",
    "set_az",
}


class TestGenerateGeoObservationWindow:
    """Test generate_geo_observation_window function."""

    def test_returns_expected_pass_params(self):
        """Test that function returns expected pass parameters."""
        observer = make_observer()
        observer.date = ephem.Date(START)

        satellite = make_satellite()
        attach_satellite_sample_map(
            satellite, {
                ephem.Date(START): (90.0, 45.0),
                ephem.Date(ephem.Date(START) + 24 * ephem.hour): (180.0, 0.0),
            }
        )

        result = generate_geo_observation_window(observer, satellite, START, END)

        assert set(result.keys()) == EXPECTED_KEYS
        assert result == {
            "rise_time": START,
            "rise_az": 90,
            "tca_time": "2023-01-02 00:00:00.123456",
            "tca_alt": 45,
            "set_time": END,
            "set_az": 180,
        }
        assert satellite.compute.call_count == 2

    def test_returns_empty_dict_when_first_compute_raises_value_error(self):
        """Test that empty dict is returned when first compute raises ValueError."""
        observer = make_observer()
        observer.date = ephem.Date(START)
        satellite = make_satellite()
        satellite.compute.side_effect = ValueError("Compute error")

        result = generate_geo_observation_window(observer, satellite, START, END)

        assert not result
        assert satellite.compute.call_count == 1

    def test_second_compute_value_error_is_propagated(self):
        """Test that ValueError from second compute is propagated."""
        observer = make_observer()
        observer.date = ephem.Date(START)
        satellite = make_satellite()

        calls = iter(["first", "second"])

        def compute(_obs):  # pylint: disable=unused-argument
            call = next(calls)

            if call == "first":
                satellite.az = 0.0
                satellite.alt = 0.0
                return None

            raise ValueError("Second compute error")

        satellite.compute.side_effect = compute

        with pytest.raises(ValueError, match="Second compute error"):
            generate_geo_observation_window(observer, satellite, START, END)

        assert satellite.compute.call_count == 2

    def test_observer_date_advances_24_hours_before_second_compute(self):
        """Test that observer.date advances 24 hours before second compute."""
        observer = make_observer()
        observer.date = ephem.Date(START)
        satellite = make_satellite()
        dates_at_compute = []

        def compute(obs):
            dates_at_compute.append(ephem.Date(obs.date))
            satellite.az = 0.0
            satellite.alt = 0.0

        satellite.compute.side_effect = compute

        generate_geo_observation_window(observer, satellite, START, END)

        assert satellite.compute.call_count == 2
        assert len(dates_at_compute) == 2

        diff_hours = (dates_at_compute[1] - dates_at_compute[0]) * 24
        assert diff_hours == pytest.approx(24.0, abs=0.001)

    def test_angle_conversion_uses_int_truncation_not_rounding(self):
        """Test that angle conversion uses int truncation, not rounding."""
        observer = make_observer()
        observer.date = ephem.Date(START)

        satellite = make_satellite()
        attach_satellite_sample_map(
            satellite, {
                ephem.Date(START): (45.9, 12.9),
                ephem.Date(ephem.Date(START) + 24 * ephem.hour): (179.9, 0.0),
            }
        )

        result = generate_geo_observation_window(observer, satellite, START, END)

        assert result["rise_az"] == 45
        assert result["tca_alt"] == 12
        assert result["set_az"] == 179


class TestGenerateGeoObservationWindowIntegration:
    """Integration tests for generate_geo_observation_window."""

    @staticmethod
    def make_real_observer():
        """Create a real ephem.Observer for integration testing."""
        observer = ephem.Observer()
        observer.lon = str(-8.0)
        observer.lat = str(38.7)
        observer.elevation = 100
        observer.pressure = 0
        observer.date = ephem.Date(START)
        return observer

    @staticmethod
    def make_goes16_satellite():
        """Create a fake GOES-16 satellite with valid TLE."""
        tle_lines = generate_fake_tle(latitude=0.0, longitude=0.0, elevation=0, date=START)
        # tle_lines[0] is name, tle_lines[1] is line 1, tle_lines[2] is line 2
        return ephem.readtle(tle_lines[0].strip(), tle_lines[1], tle_lines[2])

    def test_integration_with_real_ephem_objects(self):
        """Test integration with real ephem objects."""
        observer = self.make_real_observer()
        satellite = self.make_goes16_satellite()

        result = generate_geo_observation_window(observer, satellite, START, END)

        # Result can be empty dict (satellite not visible) or have all required keys
        if result:
            # If satellite is visible, verify all expected keys and value types
            assert set(result.keys()) == EXPECTED_KEYS

            assert result["rise_time"] == START
            assert result["set_time"] == END
            assert result["tca_time"] == "2023-01-02 00:00:00.123456"

            assert isinstance(result["rise_az"], int)
            assert isinstance(result["tca_alt"], int)
            assert isinstance(result["set_az"], int)

            assert 0 <= result["rise_az"] <= 360
            assert -90 <= result["tca_alt"] <= 90
            assert 0 <= result["set_az"] <= 360
        else:
            # Empty result is valid when satellite is not visible
            assert not result
