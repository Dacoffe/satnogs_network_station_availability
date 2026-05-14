"""Tests for scheduling functions in network.base.scheduling."""
import math
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils.timezone import now

# C0412 below clashes with isort
from network.base.scheduling import create_station_windows, \
    predict_available_observation_windows, recalculate_window_parameters, split_long_window
from network.base.test_scheduling import DEFAULT_DURATION, make_observer, make_pass, \
    make_satellite, make_scheduled_observation, make_station, make_time_window, make_tle


@pytest.mark.django_db
class TestRecalculateWindowParameters:
    """Tests for recalculate_window_parameters()."""

    def test_returns_expected_azimuths_altitude_and_restores_observer_date(self):
        """Checks the exact start azimuth, end azimuth, max altitude
        and observer.date restoration."""
        observer = make_observer()

        original_date = now().replace(microsecond=0)
        observer.date = original_date

        window_start = original_date + timedelta(seconds=10)
        window_end = window_start + timedelta(seconds=2)

        satellite = make_satellite()
        satellite_copy = MagicMock()
        satellite.copy.return_value = satellite_copy

        sample_map = {
            window_end: (120, 10),
            window_start: (30, 20),
            window_start + timedelta(seconds=1): (60, 80),
        }

        def compute_side_effect(current_observer):
            azimuth_degrees, altitude_degrees = sample_map[current_observer.date]
            satellite_copy.az = math.radians(azimuth_degrees)
            satellite_copy.alt = math.radians(altitude_degrees)

        satellite_copy.compute.side_effect = compute_side_effect

        result = recalculate_window_parameters(
            observer,
            satellite,
            window_start,
            window_end,
        )

        assert result == (30.0, 120.0, 80.0)
        assert observer.date == original_date
        satellite.copy.assert_called_once_with()

    def test_uses_copied_satellite_for_all_computations(self):
        """Verifies the function works on satellite.copy()
        and never mutates the original satellite."""
        observer = make_observer()
        observer.date = now().replace(microsecond=0)

        window_start = observer.date
        window_end = window_start + timedelta(seconds=1)

        original_satellite = make_satellite()
        satellite_copy = MagicMock()
        original_satellite.copy.return_value = satellite_copy

        sample_map = {
            window_end: (10, 20),
            window_start: (10, 20),
        }

        def compute_side_effect(current_observer):
            azimuth_degrees, altitude_degrees = sample_map[current_observer.date]
            satellite_copy.az = math.radians(azimuth_degrees)
            satellite_copy.alt = math.radians(altitude_degrees)

        satellite_copy.compute.side_effect = compute_side_effect

        result = recalculate_window_parameters(
            observer,
            original_satellite,
            window_start,
            window_end,
        )
        assert result == (10.0, 10.0, 20.0)
        original_satellite.copy.assert_called_once_with()
        original_satellite.compute.assert_not_called()
        assert satellite_copy.compute.call_count == 3

    def test_samples_each_second_before_window_end_for_max_altitude(self):
        """Verifies the helper samples every second from window_start
        up to, but not including, window_end."""
        observer = make_observer()
        observer.date = now().replace(microsecond=0)

        window_start = observer.date
        window_end = window_start + timedelta(seconds=3)

        satellite = make_satellite()
        satellite_copy = MagicMock()
        satellite.copy.return_value = satellite_copy

        sample_map = {
            window_end: (45, 5),
            window_start: (15, 10),
            window_start + timedelta(seconds=1): (90, 70),
            window_start + timedelta(seconds=2): (180, 40),
        }

        visited_dates = []

        def compute_side_effect(current_observer):
            """Attach a sample map to a mocked satellite compute method."""
            visited_dates.append(current_observer.date)
            azimuth_degrees, altitude_degrees = sample_map[current_observer.date]
            satellite_copy.az = math.radians(azimuth_degrees)
            satellite_copy.alt = math.radians(altitude_degrees)

        satellite_copy.compute.side_effect = compute_side_effect

        start_azimuth, end_azimuth, max_altitude = recalculate_window_parameters(
            observer,
            satellite,
            window_start,
            window_end,
        )

        assert start_azimuth == 15.0
        assert end_azimuth == 45.0
        assert max_altitude == 70.0
        assert visited_dates == [
            window_end,
            window_start,
            window_start,
            window_start + timedelta(seconds=1),
            window_start + timedelta(seconds=2),
        ]

    def test_end_altitude_is_not_used_for_max_altitude(self):
        """
        Documents current behaviour: max_altitude is not sampled at window_end.
        """
        observer = make_observer()
        observer.date = now().replace(microsecond=0)

        window_start = observer.date
        window_end = window_start + timedelta(seconds=2)

        satellite = make_satellite()
        satellite_copy = MagicMock()
        satellite.copy.return_value = satellite_copy

        sample_map = {
            window_end: (100, 89),
            window_start: (10, 20),
            window_start + timedelta(seconds=1): (20, 30),
        }

        def compute_side_effect(current_observer):
            azimuth_degrees, altitude_degrees = sample_map[current_observer.date]
            satellite_copy.az = math.radians(azimuth_degrees)
            satellite_copy.alt = math.radians(altitude_degrees)

        satellite_copy.compute.side_effect = compute_side_effect

        result = recalculate_window_parameters(
            observer,
            satellite,
            window_start,
            window_end,
        )

        assert result == (10.0, 100.0, 30.0)

    def test_rounds_values_to_nearest_degree(self):
        """Checks that the returned angles are rounded to whole degrees before being returned."""
        observer = make_observer()
        observer.date = now().replace(microsecond=0)

        window_start = observer.date
        window_end = window_start + timedelta(seconds=1)

        satellite = make_satellite()
        satellite_copy = MagicMock()
        satellite.copy.return_value = satellite_copy

        sample_map = {
            window_end: (120.4, 1),
            window_start: (30.6, 79.7),
        }

        def compute_side_effect(current_observer):
            azimuth_degrees, altitude_degrees = sample_map[current_observer.date]
            satellite_copy.az = math.radians(azimuth_degrees)
            satellite_copy.alt = math.radians(altitude_degrees)

        satellite_copy.compute.side_effect = compute_side_effect

        result = recalculate_window_parameters(
            observer,
            satellite,
            window_start,
            window_end,
        )

        assert result == (31.0, 120.0, 80.0)


@pytest.mark.django_db
class TestSplitLongWindow:
    """Unit tests for split_long_window()."""

    @patch("network.base.scheduling.over_min_duration", return_value=True)
    def test_returns_single_window_when_duration_is_short(self, mock_over):
        """Test that a pass shorter than split_duration is returned as a single window."""
        start, end = make_time_window(300)

        windows = split_long_window(
            start=start,
            end=end,
            duration=300,
            split_duration=600,
            break_duration=60,
        )

        assert windows == [
            {
                "start": start,
                "end": end
            },
        ]
        mock_over.assert_called_once_with(300)

    @patch("network.base.scheduling.over_min_duration", return_value=True)
    def test_splits_into_multiple_windows_with_breaks(self, mock_over):
        """Test that a long pass is split into multiple windows separated by breaks."""
        start, end = make_time_window(1000)

        windows = split_long_window(
            start=start,
            end=end,
            duration=1000,
            split_duration=300,
            break_duration=60,
        )

        assert windows == [
            {
                "start": start,
                "end": start + timedelta(seconds=300)
            },
            {
                "start": start + timedelta(seconds=360),
                "end": start + timedelta(seconds=660)
            },
            {
                "start": start + timedelta(seconds=720),
                "end": end
            },
        ]
        mock_over.assert_called_once_with(280)

    @patch("network.base.scheduling.over_min_duration", return_value=False)
    def test_drops_last_split_when_remainder_is_below_min_duration(self, mock_over):
        """Test that the final segment is dropped when its duration is below the minimum."""
        start, end = make_time_window(721)

        windows = split_long_window(
            start=start,
            end=end,
            duration=721,
            split_duration=300,
            break_duration=60,
        )

        assert windows == [
            {
                "start": start,
                "end": start + timedelta(seconds=300)
            },
            {
                "start": start + timedelta(seconds=360),
                "end": end
            },
        ]
        mock_over.assert_called_once_with(1)

    @patch("network.base.scheduling.over_min_duration", return_value=False)
    def test_returns_empty_list_when_only_split_is_below_min_duration(self, mock_over):
        """Test that an empty list is returned when even the first split is too short."""
        start, end = make_time_window(10)

        windows = split_long_window(
            start=start,
            end=end,
            duration=10,
            split_duration=300,
            break_duration=60,
        )

        assert not windows
        mock_over.assert_called_once_with(10)

    @patch("network.base.scheduling.over_min_duration", return_value=False)
    def test_handles_exact_multiple_of_split_and_break_duration(self, mock_over):
        """Test splitting when duration is an exact multiple of split plus break duration."""
        start, end = make_time_window(720)

        windows = split_long_window(
            start=start,
            end=end,
            duration=720,
            split_duration=300,
            break_duration=60,
        )

        assert windows == [
            {
                "start": start,
                "end": start + timedelta(seconds=300)
            },
            {
                "start": start + timedelta(seconds=360),
                "end": end
            },
        ]
        mock_over.assert_called_once_with(0)


@pytest.mark.django_db
class TestCreateStationWindowsBranches:
    """
    Exercise all major execution branches of create_station_windows().
    """

    @staticmethod
    def _pass_params(rise, set_, rise_az=10.0, set_az=20.0, tca_alt=30.0):
        return {
            "rise_time": rise,
            "set_time": set_,
            "rise_az": rise_az,
            "set_az": set_az,
            "tca_alt": tca_alt,
        }

    @staticmethod
    def _tle():
        return {"tle0": "0 SAT", "tle1": "1 TLE", "tle2": "2 TLE"}

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_duration_defaults_when_falsy(self, mock_recalc):
        """
        Ensure default duration settings are applied when duration is falsy.
        """
        mock_recalc.return_value = (10.0, 20.0, 30.0)

        rise, set_ = make_time_window(400)

        windows = create_station_windows(
            scheduled_obs=[],
            overlapped=1,
            pass_params=make_pass(rise, set_),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=None,
        )

        assert len(windows) >= 1

    def test_overlapped_zero_returns_empty_on_overlap(self):
        """
        Ensure overlapping passes are rejected when overlap support is disabled.
        """
        rise, set_ = make_time_window(600)

        scheduled = [
            make_scheduled_observation(
                rise + timedelta(seconds=100),
                rise + timedelta(seconds=200),
            )
        ]

        windows = create_station_windows(
            scheduled_obs=scheduled,
            overlapped=0,
            pass_params=make_pass(rise, set_),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert not windows

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_overlapped_one_with_short_partial_window(self, mock_recalc):
        """
        Ensure partially overlapped short windows are truncated correctly.
        """
        mock_recalc.return_value = (15.0, 25.0, 45.0)

        rise, set_ = make_time_window(600)

        scheduled = [
            make_scheduled_observation(
                rise + timedelta(seconds=200),
                rise + timedelta(seconds=300),
            )
        ]

        windows = create_station_windows(
            scheduled_obs=scheduled,
            overlapped=1,
            pass_params=make_pass(rise, set_),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert isinstance(windows, list)

        for window in windows:
            assert window["overlapped"] is True

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_overlapped_one_with_long_partial_window_triggers_split(self, mock_recalc):
        """
        Ensure long partially-overlapped windows are automatically split.
        """
        mock_recalc.return_value = (15.0, 25.0, 45.0)

        rise, set_ = make_time_window(2000)

        scheduled = [
            make_scheduled_observation(
                rise + timedelta(seconds=1800),
                rise + timedelta(seconds=1900),
            )
        ]

        windows = create_station_windows(
            scheduled_obs=scheduled,
            overlapped=1,
            pass_params=make_pass(rise, set_),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert len(windows) >= 2
        assert all(window["split"] is True for window in windows)

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_overlapped_two_short_pass_uses_pass_params(self, mock_recalc):
        """
        Ensure short passes reuse the original pass azimuth/elevation values.
        """
        mock_recalc.return_value = (99.0, 99.0, 99.0)

        rise, set_ = make_time_window(500)

        scheduled = [
            make_scheduled_observation(
                rise + timedelta(seconds=100),
                rise + timedelta(seconds=200),
            )
        ]

        windows = create_station_windows(
            scheduled_obs=scheduled,
            overlapped=2,
            pass_params=make_pass(
                rise,
                set_,
                rise_az=1.0,
                set_az=2.0,
                tca_alt=3.0,
            ),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert len(windows) == 1
        assert windows[0]["az_start"] == 1.0
        assert windows[0]["az_end"] == 2.0
        assert windows[0]["elev_max"] == 3.0

        mock_recalc.assert_not_called()

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_overlapped_two_long_pass_recalculates(self, mock_recalc):
        """Cobre overlapped==2 com pass longo (>720s): recalcula azimutes."""
        mock_recalc.return_value = (55.0, 66.0, 77.0)

        rise, set_ = make_time_window(1000)

        scheduled = [
            make_scheduled_observation(
                rise + timedelta(seconds=100),
                rise + timedelta(seconds=200),
            )
        ]

        windows = create_station_windows(
            scheduled_obs=scheduled,
            overlapped=2,
            pass_params=make_pass(rise, set_),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert len(windows) == 1
        assert windows[0]["az_start"] == 55.0
        assert windows[0]["az_end"] == 66.0
        assert windows[0]["elev_max"] == 77.0

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_no_overlap_short_pass_uses_pass_params(self, mock_recalc):
        """
        Ensure short non-overlapping passes preserve the original pass parameters.
        """
        mock_recalc.return_value = (99.0, 99.0, 99.0)

        rise, set_ = make_time_window(400)

        windows = create_station_windows(
            scheduled_obs=[],
            overlapped=1,
            pass_params=make_pass(
                rise,
                set_,
                rise_az=7.0,
                set_az=8.0,
                tca_alt=9.0,
            ),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert len(windows) >= 1

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_no_overlap_very_short_pass_no_split(self, mock_recalc):
        """
        Ensure very short passes are returned without triggering window splitting.
        """
        mock_recalc.return_value = (99.0, 99.0, 99.0)

        rise, set_ = make_time_window(250)

        windows = create_station_windows(
            scheduled_obs=[],
            overlapped=1,
            pass_params=make_pass(
                rise,
                set_,
                rise_az=11.0,
                set_az=22.0,
                tca_alt=33.0,
            ),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert len(windows) == 1
        assert windows[0]["az_start"] == 11.0
        assert windows[0]["az_end"] == 22.0
        assert windows[0]["elev_max"] == 33.0

        mock_recalc.assert_not_called()

    @patch("network.base.scheduling.recalculate_window_parameters")
    def test_no_overlap_long_pass_recalculates(self, mock_recalc):
        """
        Ensure azimuth and elevation values are recomputed for long passes.
        """
        mock_recalc.return_value = (44.0, 55.0, 66.0)

        rise, set_ = make_time_window(1000)

        windows = create_station_windows(
            scheduled_obs=[],
            overlapped=2,
            pass_params=make_pass(rise, set_),
            observer=make_observer(),
            satellite=make_satellite(),
            tle=make_tle(),
            duration=DEFAULT_DURATION,
        )

        assert len(windows) == 1
        assert windows[0]["az_start"] == 44.0


@pytest.mark.django_db
class TestPredictAvailableObservationWindows:
    """
    Validate pass prediction and observation window generation logic.
    The test suite covers normal passes, GEO satellites, overhead passes,
    minimum culmination filtering, pass truncation, and failure paths.
    """

    def test_returns_empty_when_compute_raises_value_error(self):
        """
        Ensure prediction returns empty results when satellite.compute() fails.
        """
        with patch("network.base.scheduling.ephem.readtle") as mock_readtle:
            satellite = make_satellite()
            mock_sat = mock_readtle.return_value = satellite

            mock_sat.compute.side_effect = ValueError("never rises")

            station = make_station()
            start, end = make_time_window(3600)

            passes, windows = predict_available_observation_windows(
                station,
                None,
                None,
                1,
                make_tle(),
                start,
                end,
                None,
            )

            assert not passes
            assert not windows

    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_no_passes_when_next_pass_raises(self, mock_next_pass, mock_readtle):
        """
        Ensure prediction stops gracefully when next_pass() cannot compute passes.
        """
        satellite = make_satellite(-0.5)

        mock_readtle.return_value = satellite
        mock_next_pass.side_effect = ValueError("no pass")

        station = make_station()

        start, end = make_time_window(3600)

        passes, windows = predict_available_observation_windows(
            station,
            None,
            None,
            1,
            make_tle(),
            start,
            end,
            None,
        )
        assert not passes
        assert not windows

    @patch("network.base.scheduling.create_station_windows")
    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_iterates_passes_until_end(self, mock_next_pass, mock_readtle, mock_create_windows):
        """
        Ensure pass prediction iterates until the scheduling end boundary.
        """
        satellite = make_satellite(-0.5)

        mock_readtle.return_value = satellite

        start, _ = make_time_window(0)
        end = start + timedelta(hours=3)

        pass1 = make_pass(
            start + timedelta(minutes=10),
            start + timedelta(minutes=20),
            rise_az=10.0,
            set_az=20.0,
            tca_alt=45.0,
        )

        pass2 = make_pass(
            end + timedelta(minutes=1),
            end + timedelta(minutes=10),
            rise_az=30.0,
            set_az=40.0,
            tca_alt=50.0,
        )

        mock_next_pass.side_effect = [pass1, pass2]
        mock_create_windows.return_value = [{"start": "x", "end": "y"}]

        station = make_station()

        passes, windows = predict_available_observation_windows(
            station,
            None,
            None,
            1,
            make_tle(),
            start,
            end,
            None,
        )

        assert len(passes) == 1
        assert len(windows) == 1

    @patch("network.base.scheduling.create_station_windows")
    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_trims_set_time_when_pass_extends_beyond_end(
        self, mock_next_pass, mock_readtle, mock_create_windows
    ):
        """
        Ensure pass end times are truncated to the scheduling boundary.
        """
        satellite = make_satellite(-0.5)

        mock_readtle.return_value = satellite

        start, _ = make_time_window(0)
        end = start + timedelta(minutes=15)

        pass1 = make_pass(
            start + timedelta(minutes=10),
            start + timedelta(minutes=20),
        )

        pass2 = make_pass(
            end + timedelta(minutes=10),
            end + timedelta(minutes=20),
        )

        mock_next_pass.side_effect = [pass1, pass2]
        mock_create_windows.return_value = []

        station = make_station()

        predict_available_observation_windows(
            station,
            None,
            None,
            1,
            make_tle(),
            start,
            end,
            None,
        )

        called_pass = mock_create_windows.call_args_list[0][0][2]

        assert called_pass["set_time"] == end

    @patch("network.base.scheduling.create_station_windows")
    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_skips_pass_below_min_culmination(
        self, mock_next_pass, mock_readtle, mock_create_windows
    ):
        """
        Ensure passes below the minimum culmination threshold are ignored.
        """
        satellite = make_satellite(-0.5)

        mock_readtle.return_value = satellite

        start, end = make_time_window(3600)

        low_pass = make_pass(
            start + timedelta(minutes=5),
            start + timedelta(minutes=10),
            tca_alt=5.0,
        )

        out_pass = make_pass(
            end + timedelta(minutes=10),
            end + timedelta(minutes=20),
            tca_alt=0.0,
        )

        mock_next_pass.side_effect = [low_pass, out_pass]

        station = make_station(
            min_culmination=50,
            min_culmination_hard_limit=True,
        )

        passes, _ = predict_available_observation_windows(
            station,
            None,
            50,
            1,
            make_tle(),
            start,
            end,
            None,
        )

        assert not passes
        mock_create_windows.assert_not_called()

    @patch("network.base.scheduling.generate_overhead_observation_window")
    @patch("network.base.scheduling.create_station_windows")
    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_satellite_currently_overhead(
        self, mock_next_pass, mock_readtle, mock_create_windows, mock_overhead
    ):
        """
        Exercise the overhead satellite scheduling path.
        """
        satellite = make_satellite(math.radians(30))

        mock_readtle.return_value = satellite

        start, end = make_time_window(3600)

        overhead_pass = make_pass(
            start,
            start + timedelta(minutes=10),
            rise_az=10.0,
            set_az=20.0,
            tca_alt=60.0,
        )

        mock_overhead.return_value = overhead_pass

        mock_next_pass.side_effect = [
            make_pass(
                start,
                start + timedelta(minutes=10),
                tca_alt=60.0,
            ),
            ValueError("end"),
        ]

        mock_create_windows.return_value = []

        station = make_station()

        passes, _ = predict_available_observation_windows(
            station,
            None,
            None,
            1,
            make_tle(),
            start,
            end,
            None,
        )

        assert len(passes) >= 1

    @patch("network.base.scheduling.generate_geo_observation_window")
    @patch("network.base.scheduling.create_station_windows")
    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_geo_satellite_path(self, mock_next_pass, mock_readtle, mock_create_windows, mock_geo):
        """
        Exercise the GEO satellite fallback path when next_pass() raises ValueError.
        """
        satellite = make_satellite(math.radians(30))

        mock_readtle.return_value = satellite
        mock_next_pass.side_effect = ValueError("geo")

        start, end = make_time_window(3600)

        mock_geo.return_value = make_pass(
            start,
            end,
            rise_az=10.0,
            set_az=20.0,
            tca_alt=60.0,
        )

        mock_create_windows.return_value = [{"start": "x", "end": "y"}]

        station = make_station()

        passes, windows = predict_available_observation_windows(
            station,
            None,
            None,
            1,
            make_tle(),
            start,
            end,
            None,
        )

        assert len(passes) == 1
        assert len(windows) == 1

    @patch("network.base.scheduling.generate_geo_observation_window")
    @patch("network.base.scheduling.ephem.readtle")
    @patch("network.base.scheduling.next_pass")
    def test_geo_path_empty_returns_early(self, mock_next_pass, mock_readtle, mock_geo):
        """
        Ensure GEO prediction exits early when no GEO window is generated.
        """
        satellite = make_satellite(math.radians(30))

        mock_readtle.return_value = satellite
        mock_next_pass.side_effect = ValueError("geo fallback")

        mock_geo.return_value = {}

        station = make_station()

        start, end = make_time_window(3600)

        passes, windows = predict_available_observation_windows(
            station,
            None,
            None,
            1,
            make_tle(),
            start,
            end,
            None,
        )

        assert not passes
        assert not windows

        mock_geo.assert_called_once()
