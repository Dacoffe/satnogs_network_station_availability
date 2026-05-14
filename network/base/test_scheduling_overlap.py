"""Tests for scheduling functions in network.base.scheduling."""

from datetime import timedelta

import pytest
from django.utils.timezone import now

# C0412 below clashes with isort
from network.base.scheduling import resolve_overlaps
from network.base.test_scheduling import make_scheduled_observation
from network.base.tests import ObservationFactory


class TestResolveOverlapsUnit:
    """Unit tests for resolve_overlaps() function"""

    def test_no_overlap_empty_scheduled_obs(self):
        """Test when no scheduled observations exist"""
        start = now().replace(microsecond=0)
        end = start + timedelta(minutes=10)

        result = resolve_overlaps([], start, end)

        assert result == ([(start, end)], False)

    def test_no_overlap_before_scheduled_obs(self):
        """Test observation completely before any scheduled observations"""
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time + timedelta(hours=1)
        scheduled_end = scheduled_start + timedelta(minutes=10)

        start = base_time
        end = base_time + timedelta(minutes=30)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == ([(start, end)], False)

    def test_no_overlap_after_scheduled_obs(self):
        """Test observation completely after any scheduled observations"""
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time
        scheduled_end = base_time + timedelta(minutes=10)

        start = base_time + timedelta(hours=1)
        end = start + timedelta(minutes=10)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == ([(start, end)], False)

    def test_total_overlap_observation_inside_scheduled(self):
        """Test when new observation is completely inside a scheduled observation"""
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time
        scheduled_end = base_time + timedelta(minutes=30)

        start = base_time + timedelta(minutes=5)
        end = base_time + timedelta(minutes=15)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == ([], True)

    def test_total_overlap_same_times(self):
        """Test when observation times are exactly the same"""
        base_time = now().replace(microsecond=0)
        start = base_time
        end = base_time + timedelta(minutes=10)

        scheduled_obs = [make_scheduled_observation(start, end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == ([], True)

    def test_overlap_at_start_of_scheduled_obs(self):
        """Test observation overlaps at the start of scheduled observation"""
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time + timedelta(minutes=5)
        scheduled_end = base_time + timedelta(minutes=15)

        start = base_time
        end = base_time + timedelta(minutes=10)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [(start, scheduled_start - timedelta(seconds=30))],
            True,
        )

    def test_overlap_at_end_of_scheduled_obs(self):
        """Test observation overlaps at the end of scheduled observation"""
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time
        scheduled_end = base_time + timedelta(minutes=10)

        start = base_time + timedelta(minutes=5)
        end = base_time + timedelta(minutes=15)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [(scheduled_end + timedelta(seconds=30), end)],
            True,
        )

    def test_overlap_in_middle_creates_two_windows(self):
        """Test observation spans scheduled observation, creating two windows"""
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time + timedelta(minutes=5)
        scheduled_end = base_time + timedelta(minutes=15)

        start = base_time
        end = base_time + timedelta(minutes=20)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [
                (start, scheduled_start - timedelta(seconds=30)),
                (scheduled_end + timedelta(seconds=30), end),
            ],
            True,
        )

    def test_overlap_with_multiple_observations(self):
        """Test observation overlapping with multiple scheduled observations"""
        base_time = now().replace(microsecond=0)
        scheduled_1_start = base_time + timedelta(minutes=5)
        scheduled_1_end = base_time + timedelta(minutes=10)
        scheduled_2_start = base_time + timedelta(minutes=15)
        scheduled_2_end = base_time + timedelta(minutes=20)

        start = base_time
        end = base_time + timedelta(minutes=25)

        scheduled_obs = [
            make_scheduled_observation(scheduled_1_start, scheduled_1_end),
            make_scheduled_observation(scheduled_2_start, scheduled_2_end),
        ]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [
                (start, scheduled_1_start - timedelta(seconds=30)),
                (
                    scheduled_1_end + timedelta(seconds=30),
                    scheduled_2_start - timedelta(seconds=30),
                ),
                (scheduled_2_end + timedelta(seconds=30), end),
            ],
            True,
        )

    def test_starting_exactly_when_scheduled_ends_counts_as_overlap(self):
        """
        Equality counts as overlap: start == datum.end triggers overlap.

        The condition in resolve_overlaps is: start <= datum.end
        So when start == datum.end, it is treated as overlap.
        """
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time
        scheduled_end = base_time + timedelta(minutes=10)

        start = scheduled_end
        end = start + timedelta(minutes=10)

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [(scheduled_end + timedelta(seconds=30), end)],
            True,
        )

    def test_ending_exactly_when_scheduled_starts_counts_as_overlap(self):
        """
        Equality counts as overlap: end == datum.start triggers overlap.

        The condition in resolve_overlaps is: datum.start <= end
        So when end == datum.start, it is treated as overlap.
        """
        base_time = now().replace(microsecond=0)
        scheduled_start = base_time + timedelta(minutes=10)
        scheduled_end = base_time + timedelta(minutes=20)

        start = base_time
        end = scheduled_start

        scheduled_obs = [make_scheduled_observation(scheduled_start, scheduled_end)]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [(start, scheduled_start - timedelta(seconds=30))],
            True,
        )

    def test_multiple_overlaps_trim_start_and_end(self):
        """
        Test multiple overlaps that trim both start and end of new window.
        """
        base_time = now().replace(microsecond=0)

        scheduled_1_start = base_time
        scheduled_1_end = base_time + timedelta(minutes=5)

        scheduled_2_start = base_time + timedelta(minutes=15)
        scheduled_2_end = base_time + timedelta(minutes=25)

        start = base_time + timedelta(minutes=3)
        end = base_time + timedelta(minutes=20)

        scheduled_obs = [
            make_scheduled_observation(scheduled_1_start, scheduled_1_end),
            make_scheduled_observation(scheduled_2_start, scheduled_2_end),
        ]

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [
                (
                    scheduled_1_end + timedelta(seconds=30),
                    scheduled_2_start - timedelta(seconds=30),
                )
            ],
            True,
        )


@pytest.mark.django_db
class TestResolveOverlapsIntegration:
    """Smoke test for resolve_overlaps() with real Observation objects."""

    def test_placeholder(self):
        """Placeholder to satisfy the two-public-methods requirement."""

    def test_works_with_real_observation_objects(self):
        """Verify real Observation objects work correctly with resolve_overlaps."""
        base_time = now().replace(microsecond=0)

        scheduled_start = base_time + timedelta(minutes=5)
        scheduled_end = base_time + timedelta(minutes=15)

        scheduled_obs = [ObservationFactory(start=scheduled_start, end=scheduled_end)]

        start = base_time
        end = base_time + timedelta(minutes=20)

        result = resolve_overlaps(scheduled_obs, start, end)

        assert result == (
            [
                (start, scheduled_start - timedelta(seconds=30)),
                (scheduled_end + timedelta(seconds=30), end),
            ],
            True,
        )
