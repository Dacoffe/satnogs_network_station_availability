"""Django base validators for SatNOGS Network"""
from collections import defaultdict
from datetime import datetime, timedelta

from django.conf import settings
from django.utils.timezone import make_aware, utc


class ObservationOverlapError(Exception):
    """Error when observation overlaps with already scheduled one"""


class OutOfRangeError(Exception):
    """Error when a frequency is out of a transmitter's or station's antenna frequency range"""


class NegativeElevationError(Exception):
    """Error when satellite doesn't raise above station's horizon"""


class SinglePassError(Exception):
    """Error when between given start and end datetimes there are more than one satellite passes"""


class NoTleSetError(Exception):
    """Error when satellite doesn't have available TLE set"""


class SchedulingLimitError(Exception):
    """Error when observations exceed scheduling limit"""


def check_start_datetime(start):
    """Validate start datetime"""
    if start < make_aware(datetime.now(), utc):
        raise ValueError("Start datetime should be in the future!")
    if start < make_aware(datetime.now() + timedelta(minutes=settings.OBSERVATION_DATE_MIN_START),
                          utc):
        raise ValueError(
            "Start datetime should be in the future, at least {0} minutes from now".format(
                settings.OBSERVATION_DATE_MIN_START
            )
        )


def check_end_datetime(end):
    """Validate end datetime"""
    if end < make_aware(datetime.now(), utc):
        raise ValueError("End datetime should be in the future!")
    max_duration = settings.OBSERVATION_DATE_MIN_START + settings.OBSERVATION_DATE_MAX_RANGE
    if end > make_aware(datetime.now() + timedelta(minutes=max_duration), utc):
        raise ValueError(
            "End datetime should be in the future, at most {0} minutes from now".
            format(max_duration)
        )


def check_start_end_datetimes(start, end):
    """Validate the pair of start and end datetimes"""
    if start > end:
        raise ValueError("End datetime should be after Start datetime!")
    if (end - start) < timedelta(seconds=settings.OBSERVATION_DURATION_MIN):
        raise ValueError(
            "Duration of observation should be at least {0} seconds".format(
                settings.OBSERVATION_DURATION_MIN
            )
        )


def downlink_is_in_range(antenna, transmitter, center_frequency=None):
    """Return true if center or transmitter frequency is in station's antenna range"""
    downlink = center_frequency or transmitter['downlink_low']
    if not downlink:
        return False
    for frequency_range in antenna.frequency_ranges.all():
        if frequency_range.min_frequency <= downlink <= frequency_range.max_frequency:
            return True
    return False


def is_transmitter_in_station_range(transmitter, station, center_frequency=None):
    """Return true if center or transmitter frequency is in one of the station's antennas ranges"""
    if transmitter["type"] == "Transponder" and center_frequency is None:
        center_frequency = (transmitter['downlink_high'] + transmitter['downlink_low']) // 2
    for gs_antenna in station.antennas.all():
        if downlink_is_in_range(gs_antenna, transmitter, center_frequency):
            return True
    return False


def is_frequency_in_transmitter_range(center_frequency, transmitter):
    """Validate whether center frequency is in transmitter range"""
    downlink_low = transmitter['downlink_low']
    downlink_high = transmitter['downlink_high']
    downlink_drift = transmitter['downlink_drift']
    if not downlink_low:
        return False
    if not downlink_high:
        return downlink_low == center_frequency
    if downlink_drift:
        if downlink_drift < 0:
            downlink_low += downlink_drift
        else:
            downlink_high += downlink_drift
    return downlink_low <= center_frequency <= downlink_high


def check_transmitter_station_pairs(transmitter_station_list):
    """Validate the pairs of transmitter and stations"""
    out_of_range_triads = []
    frequencies_out_of_transmitter_range_pairs = []

    for transmitter, station, center_frequency in transmitter_station_list:
        if center_frequency and not is_frequency_in_transmitter_range(center_frequency,
                                                                      transmitter):
            frequencies_out_of_transmitter_range_pairs.append(
                (str(transmitter['uuid']), center_frequency)
            )

        if not is_transmitter_in_station_range(transmitter, station, center_frequency):
            out_of_range_triads.append(
                (
                    str(transmitter['uuid']), int(station.id), center_frequency
                    or transmitter['downlink_low']
                )
            )

    if frequencies_out_of_transmitter_range_pairs:
        if len(frequencies_out_of_transmitter_range_pairs) == 1:
            raise OutOfRangeError(
                'Center frequency out of transmitter range.'
                ' Transmitter-frequency pair: {0}'.format(
                    frequencies_out_of_transmitter_range_pairs[0]
                )
            )
        raise OutOfRangeError(
            'Center frequency out of transmitter range.'
            ' Transmitter-frequency pairs: {0}'.format(
                len(frequencies_out_of_transmitter_range_pairs)
            )
        )

    if out_of_range_triads:
        if len(out_of_range_triads) == 1:
            raise OutOfRangeError(
                'Transmitter out of station frequency range.'
                ' Transmitter-Station-Observation Frequency triad: {0}'.format(
                    out_of_range_triads[0]
                )
            )
        raise OutOfRangeError(
            'Transmitter out of station frequency range. '
            'Transmitter-Station-Observation Frequency triads: {0}'.format(out_of_range_triads)
        )


def check_overlaps(stations_dict):
    """Check for overlaps among requested observations"""
    for station in stations_dict.keys():
        periods = stations_dict[station]
        total_periods = len(periods)
        for i in range(0, total_periods):
            start_i = periods[i][0]
            end_i = periods[i][1]
            for j in range(i + 1, total_periods):
                start_j = periods[j][0]
                end_j = periods[j][1]
                if ((start_j <= start_i <= end_j) or (start_j <= end_i <= end_j)
                        or (start_i <= start_j and end_i >= end_j)):  # noqa: W503
                    raise ObservationOverlapError(
                        'Observations of station {0} overlap'.format(station)
                    )


def return_no_fit_periods(scheduled_observations, observations_limit, time_limit):
    """
    Return periods that can not fit any other observation due to observation limit for a certain
    time limit.
    """
    scheduled_observations.sort()
    no_fit_periods = []
    obs_to_reach_limit = observations_limit - 1
    for pointer in range(0, len(scheduled_observations) - obs_to_reach_limit):
        first_obs_start = scheduled_observations[pointer]
        last_obs_start = scheduled_observations[pointer + obs_to_reach_limit]
        first_last_timedelta = last_obs_start - first_obs_start
        if first_last_timedelta.total_seconds() < time_limit:
            time_limit_period = timedelta(seconds=time_limit)
            no_fit_periods.append(
                (last_obs_start - time_limit_period, first_obs_start + time_limit_period)
            )
    return no_fit_periods


def fit_observation_into_scheduled_observations(
    observation, scheduled_observations, observations_limit, time_limit, limit_reason
):
    """
    Checks if given observation exceeds the scheduling limit and if not then appends it in given
    scheduled observations list
    """
    no_fit_periods = return_no_fit_periods(scheduled_observations, observations_limit, time_limit)
    for period in no_fit_periods:
        if period[0] <= observation <= period[1]:
            observation_start = observation.strftime("%Y-%m-%d %H:%M:%S UTC")
            period_start = period[0].strftime("%Y-%m-%d %H:%M:%S UTC")
            period_end = period[1].strftime("%Y-%m-%d %H:%M:%S UTC")
            raise SchedulingLimitError(
                (
                    'Scheduling observation that starts at {0} exceeds scheduling limit for the'
                    ' period from {1} to {2}\nReason for scheduling limit: {3}'
                ).format(observation_start, period_start, period_end, limit_reason)
            )
    scheduled_observations.append(observation)


def check_violators_scheduling_limit(violators, observations_per_norad_id):
    """
    Check if observations to be scheduled for satellite violators exceed the scheduling limit.
    """
    scheduled_observations_per_norad_id = defaultdict(list)
    time_limit = settings.OBSERVATIONS_PER_VIOLATOR_SATELLITE_PERIOD
    observations_limit = settings.OBSERVATIONS_PER_VIOLATOR_SATELLITE
    for satellite in violators:
        for observation in satellite.observations.filter(
                start__gte=make_aware(datetime.now() - timedelta(seconds=time_limit), utc)):
            scheduled_observations_per_norad_id[satellite.norad_cat_id].append(observation.start)
        for observation in observations_per_norad_id[satellite.norad_cat_id]:
            fit_observation_into_scheduled_observations(
                observation, scheduled_observations_per_norad_id[satellite.norad_cat_id],
                observations_limit, time_limit, '{0}({1}) is frequency violator satellite'.format(
                    satellite.name, satellite.norad_cat_id
                )
            )
