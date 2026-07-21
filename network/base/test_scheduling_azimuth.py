"""Tests for scheduling functions in network.base.scheduling."""
from datetime import datetime

import pytest
from django.utils.timezone import now

# C0412 below clashes with isort
from network.base.scheduling import get_azimuth
from network.base.test_scheduling import make_observer, make_satellite


@pytest.mark.django_db
class TestGetAzimuth:
    """Tests for get_azimuth() function"""

    def test_get_azimuth_returns_float_in_compass_range(self):
        """Verify get_azimuth returns float between 0-360 degrees"""
        observer = make_observer()
        satellite = make_satellite(azimuth=1.5708)  # ~90 degrees in radians
        result = get_azimuth(observer, satellite, now())

        assert isinstance(result, float)
        assert 0 <= result <= 360

    def test_get_azimuth_north_direction(self):
        """Test North direction (0 degrees)"""
        observer = make_observer()
        satellite = make_satellite(azimuth=0.0)  # North

        result = get_azimuth(observer, satellite, now())
        assert result == 0.0

    def test_get_azimuth_south_direction(self):
        """Test South direction (180 degrees)"""
        observer = make_observer()
        satellite = make_satellite(azimuth=3.14159)  # π radians = 180 degrees

        result = get_azimuth(observer, satellite, now())
        assert 179 <= result <= 181  # Allow small rounding

    def test_get_azimuth_restores_observer_date(self):
        """Critical: Verify observer.date is restored after calculation"""
        observer = make_observer()
        original_date = datetime(2023, 1, 1, 12, 0, 0)
        observer.date = original_date

        satellite = make_satellite(azimuth=1.5708)  # ~90 degrees in radians

        get_azimuth(observer, satellite, now())

        assert observer.date == original_date
