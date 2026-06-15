"""SatNOGS Network django base Forms class"""
from collections import defaultdict
from datetime import datetime
from datetime import timezone as datetime_timezone

import nh3
from django.conf import settings
from django.forms import BaseFormSet, BaseInlineFormSet, CharField, DateTimeField, DateTimeInput, \
    FloatField, Form, ImageField, IntegerField, JSONField, ModelChoiceField, ModelForm, \
    TypedChoiceField, ValidationError, formset_factory, inlineformset_factory
from django.utils import timezone

from network.base.cache import get_satellites
from network.base.db_api import DBConnectionError, get_tle_sets_by_sat_id_set, \
    get_transmitters_by_uuid_set
from network.base.models import STATION_VIOLATOR_SCHEDULING_CHOICES, Antenna, FrequencyRange, \
    Observation, Station, StationUnavailabilityPeriod
from network.base.perms import UserNoPermissionError, \
    check_schedule_perms_of_violators_per_station, check_schedule_perms_per_station
from network.base.validators import ObservationOverlapError, OutOfRangeError, check_end_datetime, \
    check_overlaps, check_start_datetime, check_start_end_datetimes, \
    check_transmitter_station_pairs


class ObservationForm(ModelForm):
    """Model Form class for Observation objects"""
    start = DateTimeField(
        input_formats=['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'],
        error_messages={
            'invalid': 'Start datetime should have either "%Y-%m-%d %H:%M:%S.%f" or '
            '"%Y-%m-%d %H:%M:%S" '
            'format.',
            'required': 'Start datetime is required.'
        }
    )
    end = DateTimeField(
        input_formats=['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'],
        error_messages={
            'invalid': 'End datetime should have either "%Y-%m-%d %H:%M:%S.%f" or '
            '"%Y-%m-%d %H:%M:%S" '
            'format.',
            'required': 'End datetime is required.'
        }
    )
    ground_station = ModelChoiceField(
        queryset=Station.objects.connected_and_located(),
        error_messages={
            'invalid_choice': 'Station(s) should exist, be available, connected '
            'and have a defined location.',
            'required': 'Station is required.'
        }
    )
    center_frequency = IntegerField(required=False)

    def clean_start(self):
        """Validates start datetime of a new observation"""
        start = self.cleaned_data['start']
        try:
            check_start_datetime(start)
        except ValueError as error:
            raise ValidationError(error, code='invalid') from error
        return start

    def clean_end(self):
        """Validates end datetime of a new observation"""
        end = self.cleaned_data['end']
        try:
            check_end_datetime(end)
        except ValueError as error:
            raise ValidationError(error, code='invalid') from error
        return end

    def clean(self):
        """Validates combination of start and end datetimes of a new observation"""
        if any(self.errors):
            # If there are errors in fields validation no need for validating the form
            return
        cleaned_data = super().clean()
        start = cleaned_data['start']
        end = cleaned_data['end']
        try:
            check_start_end_datetimes(start, end)
        except ValueError as error:
            raise ValidationError(error, code='invalid') from error

    class Meta:
        model = Observation
        fields = ['transmitter_uuid', 'start', 'end', 'ground_station', 'center_frequency']
        error_messages = {'transmitter_uuid': {'required': "Transmitter is required"}}


class BaseObservationFormSet(BaseFormSet):
    """Base FormSet class for Observation objects forms"""
    transmitters = {}
    tle_sets = set()
    violators = []

    def __init__(self, user, *args, **kwargs):
        """Initializes Observation FormSet"""
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        """Validates Observation FormSet data"""
        if any(self.errors):
            # If there are errors in forms validation no need for validating the formset
            return

        station_set = set()
        transmitter_uuid_set = set()
        transmitter_uuid_station_set = set()
        sat_id_set = set()
        uuid_to_sat_id = {}
        start_end_per_station = defaultdict(list)

        for form in self.forms:
            station = form.cleaned_data.get('ground_station')
            transmitter_uuid = form.cleaned_data.get('transmitter_uuid')
            center_frequency = form.cleaned_data.get('center_frequency', None)
            station_set.add(station)
            transmitter_uuid_set.add(transmitter_uuid)
            transmitter_uuid_station_set.add((transmitter_uuid, station, center_frequency))
            start_end_per_station[int(station.id)].append(
                (form.cleaned_data.get('start'), form.cleaned_data.get('end'))
            )

        try:
            check_overlaps(start_end_per_station)
        except ObservationOverlapError as error:
            raise ValidationError(error, code='invalid') from error

        try:
            check_schedule_perms_per_station(self.user, station_set)
        except UserNoPermissionError as error:
            raise ValidationError(error, code='forbidden') from error

        try:
            self.transmitters = get_transmitters_by_uuid_set(transmitter_uuid_set)
            for uuid in transmitter_uuid_set:
                sat_id_set.add(self.transmitters[uuid]['sat_id'])
                uuid_to_sat_id[uuid] = self.transmitters[uuid]['sat_id']
            self.tle_sets = get_tle_sets_by_sat_id_set(sat_id_set)
        except ValueError as error:
            raise ValidationError(error, code='invalid') from error
        except DBConnectionError as error:
            raise ValidationError(error) from error

        self.violators = []
        sats = get_satellites()
        for sat_id in sat_id_set:
            sat = sats[sat_id]
            if sat['is_frequency_violator']:
                self.violators.append(sat)
        violators_sat_ids = [satellite['sat_id'] for satellite in self.violators]
        station_with_violators_set = {
            station
            for transmitter_uuid, station, _ in transmitter_uuid_station_set
            if uuid_to_sat_id[transmitter_uuid] in violators_sat_ids
        }
        try:
            check_schedule_perms_of_violators_per_station(self.user, station_with_violators_set)
        except UserNoPermissionError as error:
            raise ValidationError(error, code='forbidden') from error

        transmitter_station_list = [
            (self.transmitters[transmitter_uuid], station, center_frequency)
            for transmitter_uuid, station, center_frequency in transmitter_uuid_station_set
        ]
        try:
            check_transmitter_station_pairs(transmitter_station_list)
        except OutOfRangeError as error:
            raise ValidationError(error, code='invalid') from error


ObservationFormSet = formset_factory(
    ObservationForm, formset=BaseObservationFormSet, min_num=1, validate_min=True
)


class StationRegistrationForm(ModelForm):
    """Model Form class for Station objects for Registration only"""

    def clean(self):
        """Validates Client ID"""
        if any(self.errors):
            # If there are errors in fields validation no need for validating the form
            return
        cleaned_data = super().clean()
        client_id = cleaned_data['client_id']
        try:
            Station.objects.get(client_id=client_id)
            error = (
                'Client ID is already in use, make sure'
                ' you haven\'t already register your station.'
            )
            raise ValidationError(error, code='invalid')
        except Station.DoesNotExist:
            pass

    class Meta:
        model = Station
        fields = ['name', 'description', 'client_id']


class StationForm(ModelForm):
    """Model Form class for Station objects"""
    lat = FloatField(min_value=-90.0, max_value=90.0)
    lng = FloatField(min_value=-180.0, max_value=180.0)
    violator_scheduling = TypedChoiceField(choices=STATION_VIOLATOR_SCHEDULING_CHOICES, coerce=int)
    station_configuration = JSONField(required=True)
    schema = IntegerField(required=True)

    class Meta:
        model = Station
        fields = [
            'name',
            'image',
            'alt',
            'lat',
            'lng',
            'horizon',
            'horizon_hard_limit',
            'min_culmination',
            'min_culmination_hard_limit',
            'is_available',
            'testing',
            'description',
            'target_utilization',
            'violator_scheduling',
        ]
        image = ImageField(required=False)

    def clean_description(self):
        """Filters rendered station description to only contain explicitly
        allowed html tags.
        """
        # pylint:disable=no-member
        return nh3.clean(
            html=self.cleaned_data["description"],
            tags={
                "p",
                "b",
                "i",
                "u",
                "em",
                "strong",
                "ul",
                "ol",
                "li",
                "a",
                "table",
                "thead",
                "tbody",
                "tr",
                "th",
                "td",
                "blockquote",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
            },
            attributes={
                "a": {"href", "title"},
                "th": {"colspan", "rowspan"},
                "td": {"colspan", "rowspan"},
            },
            url_schemes={"http", "https", "mailto"}
        )


class StationUnavailabilityPeriodForm(ModelForm):
    """Model Form class for StationUnavailabilityPeriod objects"""
    # required=False so that the empty "extra" formset row does not render an HTML5 required
    # attribute (which would block submission of the whole station form). The presence of both
    # datetimes for non-empty rows is enforced in clean().
    start = DateTimeField(
        required=False,
        input_formats=['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=DateTimeInput(
            format='%Y-%m-%dT%H:%M', attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }
        ),
        error_messages={'invalid': 'Start datetime should have "%Y-%m-%d %H:%M:%S" format.'}
    )
    end = DateTimeField(
        required=False,
        input_formats=['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M'],
        widget=DateTimeInput(
            format='%Y-%m-%dT%H:%M', attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }
        ),
        error_messages={'invalid': 'End datetime should have "%Y-%m-%d %H:%M:%S" format.'}
    )

    def clean(self):
        """Validates the pair of start and end datetimes of an unavailability period"""
        if any(self.errors):
            # If there are errors in fields validation no need for validating the form
            return
        cleaned_data = super().clean()
        start = cleaned_data.get('start')
        end = cleaned_data.get('end')
        if not start and not end:
            # Empty row, ignored by the formset
            return
        if not start or not end:
            raise ValidationError('Both start and end datetimes are required.', code='invalid')
        if start >= end:
            raise ValidationError('End datetime should be after start datetime.', code='invalid')
        # The end must always be in the future, so a period cannot be entirely in the past. The
        # start must be in the future only for NEW periods; an existing period may already be
        # ongoing (start in the past, end in the future) and must stay editable/re-submittable.
        now = timezone.now()
        if end < now:
            raise ValidationError('End datetime should be in the future.', code='invalid')
        if not self.instance.pk and start < now:
            raise ValidationError('Start datetime should be in the future.', code='invalid')

    class Meta:
        model = StationUnavailabilityPeriod
        fields = ['start', 'end']


class BaseStationUnavailabilityPeriodInlineFormSet(BaseInlineFormSet):
    """Base InlineFormSet class for StationUnavailabilityPeriod objects forms"""

    def get_queryset(self):
        """Returns only the editable periods: the ones whose end is still in the future
        (including ongoing periods that already started but have not ended yet). Past periods
        are excluded so they are neither rendered in the edit table nor touched on save."""
        queryset = super().get_queryset()
        now = timezone.now()
        return queryset.filter(end__gt=now)

    def clean(self):
        """Validates that the unavailability periods of a station do not overlap"""
        if any(self.errors):
            # If there are errors in forms validation no need for validating the formset
            return

        periods = []
        for form in self.forms:
            if form.cleaned_data.get('DELETE'):
                continue
            start = form.cleaned_data.get('start')
            end = form.cleaned_data.get('end')
            if not start or not end:
                continue
            periods.append((start, end))

        # Sort periods by start time and check for overlaps in O(n log n) time.
        # After sorting, if current start < previous end, there's overlap. previous_end
        # is seeded with the earliest possible (timezone-aware) datetime, so the first
        # comparison can never trigger a false overlap.
        sorted_periods = sorted(periods, key=lambda x: x[0])
        previous_end = datetime.min.replace(tzinfo=datetime_timezone.utc)
        for start, end in sorted_periods:
            if start < previous_end:
                raise ValidationError(
                    'Unavailability periods should not overlap with each other.', code='invalid'
                )
            previous_end = end


StationUnavailabilityPeriodInlineFormSet = inlineformset_factory(  # pylint: disable=C0103
    Station,
    StationUnavailabilityPeriod,
    form=StationUnavailabilityPeriodForm,
    formset=BaseStationUnavailabilityPeriodInlineFormSet,
    extra=0,
    can_delete=True,
)


AntennaInlineFormSet = inlineformset_factory(  # pylint: disable=C0103
    Station,
    Antenna,
    fields=('antenna_type', ),
    extra=0,
    can_delete=True,
    max_num=settings.MAX_ANTENNAS_PER_STATION,
    validate_max=True,
)


class BaseFrequencyRangeInlineFormSet(BaseInlineFormSet):
    """Base InlineFormSet class for FrequencyRange objects forms"""

    def clean(self):
        """Validates Observation FormSet data"""
        if any(self.errors):
            # If there are errors in forms validation no need for validating the formset
            return

        ranges = []
        for form in self.forms:
            if form.cleaned_data.get('DELETE'):
                continue
            ranges.append(
                {
                    'min': form.cleaned_data.get('min_frequency'),
                    'max': form.cleaned_data.get('max_frequency')
                }
            )

        for current_index, current_range in enumerate(ranges):
            for index, frequency_range in enumerate(ranges):
                if index == current_index:
                    continue
                if (frequency_range['min'] < current_range['min']
                        and frequency_range['max'] > current_range['max']):
                    raise ValidationError(
                        'Frequency Range {0}-{1} is subset of another'
                        ' antenna frequency range ({2}-{3})'.format(
                            current_range['min'], current_range['max'], frequency_range['min'],
                            frequency_range['max']
                        ),
                        code='invalid'
                    )
                if (frequency_range['min'] > current_range['min']
                        and frequency_range['max'] < current_range['max']):
                    raise ValidationError(
                        'Frequency Range {0}-{1} is superset of another'
                        ' antenna frequency range ({2}-{3})'.format(
                            current_range['min'], current_range['max'], frequency_range['min'],
                            frequency_range['max']
                        ),
                        code='invalid'
                    )
                if not (frequency_range['min'] > current_range['max']
                        or frequency_range['max'] < current_range['min']):
                    raise ValidationError(
                        'Frequency Range {0}-{1} conflicts with another'
                        ' antenna frequency range ({2}-{3})'.format(
                            current_range['min'], current_range['max'], frequency_range['min'],
                            frequency_range['max']
                        ),
                        code='invalid'
                    )


FrequencyRangeInlineFormSet = inlineformset_factory(  # pylint: disable=C0103
    Antenna,
    FrequencyRange,
    fields=(
        'min_frequency',
        'max_frequency',
    ),
    formset=BaseFrequencyRangeInlineFormSet,
    extra=0,
    can_delete=True,
    max_num=settings.MAX_FREQUENCY_RANGES_PER_ANTENNA,
    validate_max=True,
)


class SatelliteFilterForm(Form):
    """Form class for Satellite objects"""
    sat_id = CharField(required=False)
    start = CharField(required=False)
    end = CharField(required=False)
    ground_station = IntegerField(required=False)
    transmitter = CharField(required=False)
