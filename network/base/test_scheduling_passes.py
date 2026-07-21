"""Tests for scheduling functions in network.base.scheduling."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

# C0412 below clashes with isort
from network.base.scheduling import next_pass, over_min_duration


@pytest.mark.django_db
class TestOverMinDuration:
    """Tests for over_min_duration() function"""

    def test_over_min_duration_exact_minimum(self):
        """Test duration exactly at minimum threshold"""
        min_duration = settings.OBSERVATION_DURATION_MIN

        result = over_min_duration(min_duration)

        assert result is True

    def test_over_min_duration_below_minimum(self):
        """Test duration below minimum requirement"""
        min_duration = settings.OBSERVATION_DURATION_MIN

        result = over_min_duration(min_duration - 1)

        assert result is False

    def test_over_min_duration_well_above_minimum(self):
        """Test duration well above minimum"""
        min_duration = settings.OBSERVATION_DURATION_MIN

        result = over_min_duration(min_duration + 1000)

        assert result is True

    def test_over_min_duration_zero_duration(self):
        """Test zero duration (edge case)"""
        result = over_min_duration(0)

        assert result is False


@pytest.mark.django_db
class TestNextPass:
    """Tests for next_pass() function"""

    @patch('network.base.scheduling.ephem.Date')
    def test_next_pass_returns_required_keys(self, mock_date_class):
        """Verify next_pass returns a dict with all six expected keys."""
        observer = MagicMock()
        observer.next_pass.return_value = (1234567890, 0.1, 1234567900, 0.785, 1234567910, 0.2)

        satellite = MagicMock()

        mock_date_class.side_effect = lambda ts: MagicMock(
            datetime=MagicMock(return_value=datetime(2023, 1, 1, 12, 0, 0))
        )

        result = next_pass(observer, satellite)

        assert set(result.keys()) == {
            'rise_time',
            'set_time',
            'tca_time',
            'rise_az',
            'set_az',
            'tca_alt',
        }

    @patch('network.base.scheduling.ephem.Date')
    def test_next_pass_times_are_ordered(self, mock_date_class):
        """Verify rise_time < tca_time < set_time"""

        observer = MagicMock()
        observer.next_pass.return_value = (1000, 0.1, 2000, 0.785, 3000, 0.2)

        def mock_date(ts):
            """Return a mock date object from a timestamp."""
            return MagicMock(datetime=MagicMock(return_value=datetime.utcfromtimestamp(ts)))

        mock_date_class.side_effect = mock_date

        satellite = MagicMock()

        result = next_pass(observer, satellite)

        assert result['rise_time'] < result['tca_time'] < result['set_time']

    @patch('network.base.scheduling.ephem.Date')
    def test_next_pass_handles_geo_satellite_error(self, mock_date_class):
        """Test error handling for GEO satellites (raises ValueError)"""

        observer = MagicMock()
        observer.next_pass.side_effect = ValueError("satellite never rises above horizon")

        satellite = MagicMock()

        mock_date_class.side_effect = lambda ts: MagicMock(
            datetime=MagicMock(return_value=datetime(2023, 1, 1, 12, 0, 0))
        )

        with pytest.raises(ValueError, match="satellite never rises"):
            next_pass(observer, satellite)

    @patch('network.base.scheduling.ephem.Date')
    def test_next_pass_respects_singlepass_parameter(self, mock_date_class):
        """Verify singlepass parameter is correctly passed to observer.next_pass()"""

        observer = MagicMock()
        observer.next_pass.return_value = (1234567890, 0.1, 1234567900, 0.785, 1234567910, 0.2)

        mock_date_class.side_effect = lambda ts: MagicMock(
            datetime=MagicMock(return_value=datetime(2023, 1, 1, 12, 0, 0))
        )

        satellite = MagicMock()

        # Test True
        next_pass(observer, satellite, singlepass=True)
        observer.next_pass.assert_called_with(satellite, True)

        observer.next_pass.reset_mock()

        # Test False
        next_pass(observer, satellite, singlepass=False)
        observer.next_pass.assert_called_with(satellite, False)

    @patch('network.base.scheduling.ephem.Date')
    def test_next_pass_azimuth_in_valid_range(self, mock_date_class):
        """Verify azimuths are converted correctly to degrees (0-360)"""

        observer = MagicMock()
        pass_data = (1234567890, 1.5708, 1234567900, 0.785, 1234567910, 3.1416)
        observer.next_pass.return_value = pass_data

        mock_date_class.side_effect = lambda ts: MagicMock(
            datetime=MagicMock(return_value=datetime(2023, 1, 1, 12, 0, 0))
        )

        satellite = MagicMock()

        result = next_pass(observer, satellite)

        assert 0 <= result['rise_az'] <= 360
        assert 0 <= result['set_az'] <= 360
        assert 0 <= result['tca_alt'] <= 90
