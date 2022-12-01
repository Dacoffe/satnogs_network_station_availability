"""SatNOGS Network django base Forms class"""
from collections import defaultdict

from django.conf import settings
from django.forms import BaseFormSet, BaseInlineFormSet, CharField, DateTimeField, FloatField, \
    Form, ImageField, IntegerField, ModelChoiceField, ModelForm, TypedChoiceField, \
    ValidationError, formset_factory, inlineformset_factory

from network.base.db_api import DBConnectionError, get_tle_sets_by_norad_id_set, \
    get_transmitters_by_uuid_set
from network.base.models import STATION_VIOLATOR_SCHEDULING_CHOICES, Antenna, FrequencyRange, \
    Observation, Satellite, Station
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
        queryset=Station.objects.filter(
            status__gt=0, alt__isnull=False, lat__isnull=False, lng__isnull=False
        ),
        error_messages={
            'invalid_choice': 'Station(s) should exist, be online and have a defined location.',
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
        norad_id_set = set()
        uuid_to_norad_id = {}
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
                norad_id_set.add(self.transmitters[uuid]['norad_cat_id'])
                uuid_to_norad_id[uuid] = self.transmitters[uuid]['norad_cat_id']
            self.tle_sets = get_tle_sets_by_norad_id_set(norad_id_set)
        except ValueError as error:
            raise ValidationError(error, code='invalid') from error
        except DBConnectionError as error:
            raise ValidationError(error) from error

        self.violators = Satellite.objects.filter(
            norad_cat_id__in=norad_id_set, is_frequency_violator=True
        )
        violators_norad_ids = [satellite.norad_cat_id for satellite in self.violators]
        station_with_violators_set = {
            station
            for transmitter_uuid, station, _ in transmitter_uuid_station_set
            if uuid_to_norad_id[transmitter_uuid] in violators_norad_ids
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

    class Meta:
        model = Station
        fields = [
            'name', 'image', 'alt', 'lat', 'lng', 'qthlocator', 'horizon', 'testing',
            'description', 'target_utilization', 'violator_scheduling', 'satnogs_soapy_rx_device',
            'satnogs_antenna', 'satnogs_rx_samp_rate', 'satnogs_rf_gain'
        ]
        image = ImageField(required=False)


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
    norad = IntegerField(required=False)
    start = CharField(required=False)
    end = CharField(required=False)
    ground_station = IntegerField(required=False)
    transmitter = CharField(required=False)
