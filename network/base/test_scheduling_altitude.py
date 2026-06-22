"""Tests for scheduling functions in network.base.scheduling."""
from datetime import datetime

import pytest
from django.utils.timezone import now

from network.base.scheduling import get_altitude
from network.base.test_scheduling import make_observer, make_satellite


@pytest.mark.django_db
class TestGetAltitude:
    """Tests for get_altitude() function"""

    def test_get_altitude_returns_float(self):
        """Verify get_altitude returns float value in degrees"""
        observer = make_observer()
        satellite = make_satellite(1.571)  # ~90 degrees in radians

        result = get_altitude(observer, satellite, now())

        assert isinstance(result, float)
        assert 0 <= result <= 90

    def test_get_altitude_negative_elevation(self):
        """Test satellite below horizon (negative altitude)"""
        observer = make_observer()
        satellite = make_satellite(-0.7854)  # ~-45 degrees in radians

        result = get_altitude(observer, satellite, now())

        assert isinstance(result, float)
        assert result < 0

    def test_get_altitude_restores_observer_date(self):
        """Critical: Verify observer.date is restored after calculation"""
        observer = make_observer()
        original_date = datetime(2023, 1, 1, 12, 0, 0)
        observer.date = original_date

        satellite = make_satellite(0.5)

        get_altitude(observer, satellite, now())

        assert observer.date == original_date
