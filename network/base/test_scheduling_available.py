"""Comprehensive Tests for get_available_stations() Function"""
from unittest.mock import Mock

import pytest

from network.base.models import Antenna, AntennaType, FrequencyRange, Station
from network.base.scheduling import get_available_stations
from network.base.test_scheduling import add_frequency_range_to_station

pytest_plugins = ['network.base.test_scheduling']


class TestGetAvailableStationsBasic:
    """Test basic filtering and early returns"""

    @pytest.mark.usefixtures('antenna_vhf')
    def test_no_downlink_returns_empty(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that when downlink is None/empty, no stations are returned"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=None,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result

    def test_station_without_antennas_returns_empty(
        self,
        user,
        station_no_antennas,
        monkeypatch,
    ):
        """Test that station without antennas returns no results"""
        stations = Station.objects.filter(id=station_no_antennas.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_no_antennas.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result

    @pytest.mark.usefixtures('antenna_vhf')
    def test_no_user_permissions_returns_empty(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that stations without user permissions are excluded"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: False}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result


class TestGetAvailableStationsFrequency:
    """Test frequency range matching"""

    @pytest.mark.usefixtures('antenna_vhf')
    def test_downlink_within_range_returns_station(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that downlink within antenna range returns the station"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,  # Within 145-146 MHz
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert [station.id for station in result] == [station_basic.id]

    @pytest.mark.usefixtures('antenna_vhf')
    def test_downlink_at_min_boundary_returns_station(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that downlink at minimum frequency boundary is included"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145000000,  # Minimum boundary
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert [station.id for station in result] == [station_basic.id]

    @pytest.mark.usefixtures('antenna_vhf')
    def test_downlink_at_max_boundary_returns_station(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that downlink at maximum frequency boundary is included"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=146000000,  # Maximum boundary
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert [station.id for station in result] == [station_basic.id]

    @pytest.mark.usefixtures('antenna_vhf')
    def test_downlink_below_range_returns_empty(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that downlink below range excludes station"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=144999999,  # Just below 145 MHz
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result

    @pytest.mark.usefixtures('antenna_vhf')
    def test_downlink_above_range_returns_empty(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that downlink above range excludes station"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=146000001,  # Just above 146 MHz
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result


class TestGetAvailableStationsMultipleAntennas:
    """Test behavior with multiple antennas on a station"""

    @pytest.mark.usefixtures('antenna_vhf', 'antenna_uhf')
    def test_frequency_found_in_second_antenna(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that frequency is found if any antenna supports it"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        # UHF frequency - should match antenna_uhf, not antenna_vhf
        result = get_available_stations(
            stations=stations,
            downlink=436500000,  # Within UHF range (435-438 MHz)
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert [station.id for station in result] == [station_basic.id]

    @pytest.mark.usefixtures('antenna_vhf', 'antenna_uhf')
    def test_frequency_not_in_any_antenna_returns_empty(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that station is excluded if no antenna supports frequency"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        # S-band frequency - not supported by any antenna
        result = get_available_stations(
            stations=stations,
            downlink=2410000000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result


class TestGetAvailableStationsViolator:
    """Test filtering based on violator_scheduling and user permissions"""

    def test_non_violator_satellite_all_stations_included(
        self,
        user,
        station_basic,
        station_violator_restricted,
        station_violator_special_perm,
        monkeypatch,
    ):
        """Test that non-violator satellites bypass violator_scheduling filters"""
        stations = Station.objects.filter(
            id__in=[
                station_basic.id,
                station_violator_restricted.id,
                station_violator_special_perm.id,
            ]
        )

        # Add antennas to all stations using helper
        for station in [station_basic, station_violator_restricted, station_violator_special_perm]:
            add_frequency_range_to_station(station)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(
                return_value={
                    station_basic.id: True,
                    station_violator_restricted.id: True,
                    station_violator_special_perm.id: True,
                }
            ),
        )
        # For non-violator, has_perm_to_schedule_violator should NOT be called
        mock_has_perm = Mock(return_value=False)

        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            mock_has_perm,
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        # All stations should be included
        result_ids = {station.id for station in result}
        assert result_ids == {
            station_basic.id,
            station_violator_restricted.id,
            station_violator_special_perm.id,
        }
        mock_has_perm.assert_not_called()

    def test_violator_excludes_violator_scheduling_0(
        self,
        user,
        station_basic,
        station_violator_restricted,
        monkeypatch,
    ):
        """Test that violator satellites exclude stations with violator_scheduling=0"""
        stations = Station.objects.filter(
            id__in=[station_basic.id, station_violator_restricted.id]
        )

        # Add antenna to both stations using helper
        add_frequency_range_to_station(station_basic)
        add_frequency_range_to_station(station_violator_restricted)

        mock_has_perm = Mock(return_value=False)
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={
                station_basic.id: True,
                station_violator_restricted.id: True,
            }),
        )
        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            mock_has_perm,
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': True},
        )

        # Only basic station should be included
        assert [station.id for station in result] == [station_basic.id]
        mock_has_perm.assert_called_once_with(user)

    def test_violator_violator_scheduling_1_includes_with_permission(
        self,
        user,
        station_violator_special_perm,
        monkeypatch,
    ):
        """Test that violator_scheduling=1 includes station if user has permission"""
        stations = Station.objects.filter(id=station_violator_special_perm.id)

        # Add antenna using helper
        add_frequency_range_to_station(station_violator_special_perm)

        mock_has_perm = Mock(return_value=True)
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_violator_special_perm.id: True}),
        )
        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            mock_has_perm,
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': True},
        )

        assert [station.id for station in result] == [station_violator_special_perm.id]
        mock_has_perm.assert_called_once_with(user)

    def test_violator_violator_scheduling_1_excludes_without_permission(
        self,
        user,
        station_violator_special_perm,
        monkeypatch,
    ):
        """Test that violator_scheduling=1 excludes station if user lacks permission"""
        stations = Station.objects.filter(id=station_violator_special_perm.id)

        # Add antenna
        add_frequency_range_to_station(station_violator_special_perm)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_violator_special_perm.id: True}),
        )
        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            Mock(return_value=False),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': True},
        )

        assert not result

    @pytest.mark.usefixtures('antenna_vhf')
    def test_non_violator_satellite_does_not_call_has_perm(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that has_perm_to_schedule_violator is NOT called for non-violators"""
        stations = Station.objects.filter(id=station_basic.id)

        mock_has_perm = Mock(return_value=False)
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )
        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            mock_has_perm,
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert [station.id for station in result] == [station_basic.id]
        mock_has_perm.assert_not_called()

    def test_violator_all_scheduling_levels_mixed_permissions(
        self,
        user,
        station_basic,
        station_violator_restricted,
        station_violator_special_perm,
        monkeypatch,
    ):
        """Integration test: all three violator_scheduling levels with different
        permission levels"""
        stations = Station.objects.filter(
            id__in=[
                station_basic.id,
                station_violator_restricted.id,
                station_violator_special_perm.id,
            ]
        )

        # Add antennas to all stations
        for station in [station_basic, station_violator_restricted, station_violator_special_perm]:
            add_frequency_range_to_station(station)

        mock_has_perm = Mock(return_value=True)  # User HAS special permission
        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            mock_has_perm,
        )
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(
                return_value={
                    station_basic.id: True,
                    station_violator_restricted.id: True,
                    station_violator_special_perm.id: True,
                }
            ),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': True},
        )

        # With permission:
        # - violator_scheduling=2 (basic) → included
        # - violator_scheduling=0 (restricted) → excluded (always)
        # - violator_scheduling=1 (special) → included (because user has permission)
        result_ids = {station.id for station in result}

        assert station_basic.id in result_ids
        assert station_violator_restricted.id not in result_ids
        assert station_violator_special_perm.id in result_ids
        mock_has_perm.assert_called_once_with(user)


class TestGetAvailableStationsEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.usefixtures('antenna_vhf')
    def test_zero_downlink_treated_as_no_downlink(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that downlink=0 is treated as falsy and returns empty"""
        stations = Station.objects.filter(id=station_basic.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station_basic.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=0,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        assert not result

    def test_overlapping_frequency_ranges_does_not_duplicate_station(
        self,
        user,
        monkeypatch,
    ):
        """Test that if multiple antenna ranges match, station appears only once."""
        station = Station.objects.create(
            name='Overlapping Ranges Station',
            lng=10.0,
            lat=40.0,
            alt=100,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )

        # Create antenna with overlapping ranges
        antenna_type, _ = AntennaType.objects.get_or_create(name='Overlapping Antenna')
        antenna = Antenna.objects.create(station=station, antenna_type=antenna_type)

        # Range 1: 145.0 - 146.0 MHz
        FrequencyRange.objects.create(
            antenna=antenna,
            min_frequency=145000000,
            max_frequency=146000000,
        )
        # Range 2: 145.2 - 145.8 MHz (overlaps with Range 1)
        FrequencyRange.objects.create(
            antenna=antenna,
            min_frequency=145200000,
            max_frequency=145800000,
        )

        stations = Station.objects.filter(id=station.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station.id: True}),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,  # Matches both ranges
            user=user,
            satellite={'is_frequency_violator': False},
        )

        # Station should appear only once, not twice
        result_ids = [returned_station.id for returned_station in result]
        assert result_ids == [station.id]
        assert len(result) == 1

    def test_missing_permission_entry_raises_key_error(
        self,
        user,
        station_basic,
        monkeypatch,
    ):
        """Test that missing permission entry raises KeyError."""
        stations = Station.objects.filter(id=station_basic.id)

        # Return empty dict - station_basic.id is missing
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={}),
        )

        with pytest.raises(KeyError):
            get_available_stations(
                stations=stations,
                downlink=145500000,
                user=user,
                satellite={'is_frequency_violator': False},
            )


class TestGetAvailableStationsIntegration:
    """Integration tests combining multiple filtering factors"""

    def test_full_filtering_scenario_combines_all_factors(
        self,
        user,
        monkeypatch,
    ):
        """Integration test: each station fails for a different reason.

        - valid_station: passes all filters
        - blocked_by_violator_station: excluded due to violator_scheduling=0
        - blocked_by_frequency_station: excluded due to wrong frequency
        - blocked_by_permission_station: excluded due to no user permission
        """
        valid_station = Station.objects.create(
            name='Valid Station',
            lng=10.0,
            lat=40.0,
            alt=100,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )
        add_frequency_range_to_station(valid_station)

        blocked_by_violator = Station.objects.create(
            name='Blocked By Violator Station',
            lng=11.0,
            lat=41.0,
            alt=100,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=0,
        )
        add_frequency_range_to_station(blocked_by_violator)

        blocked_by_frequency = Station.objects.create(
            name='Blocked By Frequency Station',
            lng=12.0,
            lat=42.0,
            alt=100,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )
        add_frequency_range_to_station(
            blocked_by_frequency,
            min_frequency=435000000,
            max_frequency=438000000,
        )

        blocked_by_permission = Station.objects.create(
            name='Blocked By Permission Station',
            lng=13.0,
            lat=43.0,
            alt=100,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )
        add_frequency_range_to_station(blocked_by_permission)

        stations = Station.objects.filter(
            id__in=[
                valid_station.id,
                blocked_by_violator.id,
                blocked_by_frequency.id,
                blocked_by_permission.id,
            ]
        )

        monkeypatch.setattr(
            'network.base.scheduling.has_perm_to_schedule_violator',
            Mock(return_value=True),
        )

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(
                return_value={
                    valid_station.id: True,
                    blocked_by_frequency.id: True,
                    blocked_by_permission.id: False,
                }
            ),
        )

        result = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': True},
        )

        # Only valid_station should be in result
        assert [station.id for station in result] == [valid_station.id]

    def test_multiple_frequency_ranges_same_antenna(
        self,
        user,
        station_with_multiple_frequency_ranges,
        monkeypatch,
    ):
        """Test station with antenna having multiple non-overlapping frequency ranges"""
        station = station_with_multiple_frequency_ranges
        stations = Station.objects.filter(id=station.id)

        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={station.id: True}),
        )

        # Test VHF frequency
        result_vhf = get_available_stations(
            stations=stations,
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )
        vhf_ids = [returned_station.id for returned_station in result_vhf]
        assert vhf_ids == [station.id]

        # Test UHF frequency
        result_uhf = get_available_stations(
            stations=stations,
            downlink=436500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )
        uhf_ids = [returned_station.id for returned_station in result_uhf]
        assert uhf_ids == [station.id]

        # Test S-band frequency
        result_sband = get_available_stations(
            stations=stations,
            downlink=2420000000,
            user=user,
            satellite={'is_frequency_violator': False},
        )
        sband_ids = [returned_station.id for returned_station in result_sband]
        assert sband_ids == [station.id]

    def test_large_dataset_filtering(self, user, monkeypatch):
        """Integration test with multiple stations and various constraints"""
        # Create multiple stations with different configurations
        stations_list = []

        for i in range(5):
            station = Station.objects.create(
                name=f'Station {i}',
                lng=10.0 + i,
                lat=40.0 + i,
                alt=100 + i * 50,
                horizon=10,
                min_culmination=10,
                testing=False,
                violator_scheduling=2,
            )

            # Add antenna with 145-146 MHz range to even stations using helper
            if i % 2 == 0:
                add_frequency_range_to_station(
                    station,
                    antenna_type_name=f'Antenna {i}',
                )

            stations_list.append(station)

        station_ids = {s.id: True for s in stations_list}
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value=station_ids),
        )

        result = get_available_stations(
            stations=Station.objects.filter(id__in=[s.id for s in stations_list]),
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        # Only stations with even indices should be returned (0, 2, 4)
        assert len(result) == 3
        result_ids = {s.id for s in result}
        for i, station in enumerate(stations_list):
            if i % 2 == 0:
                assert station.id in result_ids
            else:
                assert station.id not in result_ids

    def test_partial_permissions_mixed_antennas(self, user, monkeypatch):
        """Test with mixed permissions and antenna configurations"""
        # Create 3 stations with different permission levels
        station1 = Station.objects.create(
            name='Permitted Station',
            lng=10.0,
            lat=40.0,
            alt=100,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )

        station2 = Station.objects.create(
            name='No Permission Station',
            lng=15.0,
            lat=45.0,
            alt=150,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )

        station3 = Station.objects.create(
            name='Partial Permission Station',
            lng=20.0,
            lat=50.0,
            alt=200,
            horizon=10,
            min_culmination=10,
            testing=False,
            violator_scheduling=2,
        )

        # Add antennas to all stations using helper
        for station in [station1, station2, station3]:
            add_frequency_range_to_station(station)

        # User has permission only for station1 and station3
        monkeypatch.setattr(
            'network.base.scheduling.get_schedule_permissions_per_station',
            Mock(return_value={
                station1.id: True,
                station2.id: False,
                station3.id: True,
            }),
        )

        result = get_available_stations(
            stations=Station.objects.filter(id__in=[station1.id, station2.id, station3.id]),
            downlink=145500000,
            user=user,
            satellite={'is_frequency_violator': False},
        )

        # Only station1 and station3 should be returned
        result_ids = {s.id for s in result}
        assert station1.id in result_ids
        assert station2.id not in result_ids
        assert station3.id in result_ids
        assert len(result) == 2
