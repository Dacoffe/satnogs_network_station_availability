"""Django database base model for SatNOGS Network"""
import codecs
import re
from datetime import timedelta
from operator import truth

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.storage import DefaultStorage
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, \
    MinValueValidator
from django.db import models
from django.db.models import Count, Q
from django.dispatch import receiver
from django.urls import reverse
from django.utils.timezone import now
from shortuuidfield import ShortUUIDField
from storages.backends.s3boto3 import S3Boto3Storage

from network.base.db_api import DBConnectionError, get_artifact_metadata_by_observation_id
from network.base.managers import ObservationManager, StationManagerQueryset
from network.base.utils import bands_from_range

User = get_user_model()

STATION_STATUSES = (
    (2, 'Online'),
    (1, 'Testing'),
    (0, 'Offline'),
)
STATION_VIOLATOR_SCHEDULING_CHOICES = (
    (0, 'No one'),
    (1, 'Only Operators'),
    (2, 'Everyone'),
)
SATELLITE_STATUS = ['in orbit', 'future', 're-entered']
TRANSMITTER_STATUS = ['active', 'inactive', 'invalid']
TRANSMITTER_TYPE = ['Transmitter', 'Transceiver', 'Transponder']


def _decode_pretty_hex(binary_data):
    """Return the binary data as hex dump of the following form: `DE AD C0 DE`"""

    data = codecs.encode(binary_data, 'hex').decode('ascii').upper()
    return ' '.join(data[i:i + 2] for i in range(0, len(data), 2))


def _name_obs_files(instance, filename):
    """Return a filepath formatted by Observation ID"""
    return 'data_obs/{0}/{1}'.format(instance.id, filename)


def _name_obs_demoddata(instance, filename):
    """Return a filepath for DemodData formatted by Observation ID"""
    # On change of the string bellow, change it also at api/views.py
    return 'data_obs/{0}/{1}'.format(instance.observation.id, filename)


def _name_observation_data(instance, filename):
    """Return a filepath formatted by Observation ID"""
    return 'data_obs/{0}/{1}/{2}/{3}/{4}/{5}'.format(
        instance.start.year, instance.start.month, instance.start.day, instance.start.hour,
        instance.id, filename
    )


def _name_observation_demoddata(instance, filename):
    """Return a filepath for DemodData formatted by Observation ID"""
    # On change of the string bellow, change it also at api/views.py
    return 'data_obs/{0}/{1}/{2}/{3}/{4}/{5}'.format(
        instance.observation.start.year, instance.observation.start.month,
        instance.observation.start.day, instance.observation.start.hour, instance.observation.id,
        filename
    )


def _select_audio_storage():
    return S3Boto3Storage() if settings.USE_S3_STORAGE_FOR_AUDIO else DefaultStorage()


def _select_waterfall_storage():
    return S3Boto3Storage() if settings.USE_S3_STORAGE_FOR_WATERFALL else DefaultStorage()


def _select_data_storage():
    return S3Boto3Storage() if settings.USE_S3_STORAGE_FOR_DATA else DefaultStorage()


def validate_image(fieldfile_obj):
    """Validates image size"""
    filesize = fieldfile_obj.file.size
    megabyte_limit = 2.0
    if filesize > megabyte_limit * 1024 * 1024:
        raise ValidationError("Max file size is %sMB" % str(megabyte_limit))


def get_default_station_configuration_schema():
    """Generate default value for schema field of StationConfigurationSchema model"""
    return {}


def get_default_station_configuration():
    """Generate default value for schema field of StationConfiguration model"""
    return {}


class StationType(models.Model):
    """Model for SatNOGS station types"""
    name = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.name


class StationConfigurationSchema(models.Model):
    """Model for SatNOGS station configuration schemas"""
    name = models.CharField(max_length=100)
    station_type = models.ForeignKey('StationType', on_delete=models.CASCADE)
    schema = models.JSONField(default=get_default_station_configuration_schema)

    def __str__(self):
        return self.station_type.name + ' - ' + self.name

    class Meta:
        unique_together = ['name', 'station_type']


class StationConfiguration(models.Model):
    """Model for SatNOGS station configuration schemas"""
    name = models.CharField(max_length=100)
    station = models.ForeignKey('Station', on_delete=models.CASCADE)
    schema = models.ForeignKey('StationConfigurationSchema', on_delete=models.CASCADE)
    configuration = models.JSONField(default=get_default_station_configuration)
    active = models.BooleanField(default=True)
    applied = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ActiveStationConfigurationManager(models.Manager):  # pylint: disable=R0903
    """Django Manager for ActiveStationConfiguration objects"""

    def get_queryset(self):
        """Returns query of StationConfigurations

        :returns: the active configurations for stations
        """
        return super().get_queryset().filter(active=True)


class ActiveStationConfiguration(StationConfiguration):
    """Proxy model for StationConfiguration that contains only active ones"""
    objects = ActiveStationConfigurationManager()

    class Meta:
        proxy = True


class Station(models.Model):
    """Model for SatNOGS ground stations."""
    owner = models.ForeignKey(
        User, related_name="ground_stations", on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=45)
    image = models.ImageField(upload_to='ground_stations', blank=True, validators=[validate_image])
    alt = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-500)],
        help_text='In meters above sea level'
    )
    lat = models.FloatField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(90), MinValueValidator(-90)],
        help_text='eg. 38.01697'
    )
    lng = models.FloatField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(180), MinValueValidator(-180)],
        help_text='eg. 23.7314'
    )
    featured_date = models.DateField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    is_available = models.BooleanField(default=True)
    testing = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    violator_scheduling = models.IntegerField(
        choices=STATION_VIOLATOR_SCHEDULING_CHOICES, default=0
    )
    # Allows 0
    horizon = models.PositiveIntegerField(help_text='In degrees above 0', default=10)
    horizon_hard_limit = models.BooleanField(default=False)
    # Allows 0
    min_culmination = models.PositiveIntegerField(help_text='In degrees above 0', default=10)
    min_culmination_hard_limit = models.BooleanField(default=False)
    description = models.TextField(max_length=2000, blank=True, help_text='Max 2000 characters')
    client_version = models.CharField(max_length=45, blank=True)
    target_utilization = models.IntegerField(
        validators=[MaxValueValidator(100), MinValueValidator(0)],
        help_text='Target utilization factor for '
        'your station',
        null=True,
        blank=True
    )
    client_id = models.UUIDField(null=True, blank=True, editable=True, db_index=True)
    active_configuration_changed = models.DateTimeField(blank=True, null=True)

    objects = StationManagerQueryset.as_manager()

    class Meta:
        indexes = [models.Index(fields=['last_seen'])]

    def get_allowed_horizon(self, requested_horizon: int | None) -> int:
        """Returns the minumum allowed horizon value given a requested value"""
        if requested_horizon is None:
            return self.horizon
        if not isinstance(requested_horizon, int):
            raise TypeError("requested_horizon must be an int")
        if not requested_horizon >= 0:
            raise ValueError("requested_horizon must be non-negative")
        hard_limit = self.horizon_hard_limit
        if not hard_limit:
            return requested_horizon
        return max(requested_horizon, self.horizon)

    def get_allowed_min_culmination(self, requested_min_culmination: int | None) -> int:
        """Returns the minumum allowed min_culmination value given a requested value"""
        if requested_min_culmination is None:
            return self.min_culmination
        if not isinstance(requested_min_culmination, int):
            raise TypeError("requested_min_culmination must be an int")
        if not requested_min_culmination >= 0:
            raise ValueError("requested_min_culmination must be non-negative")
        hard_limit = self.min_culmination_hard_limit
        if not hard_limit:
            return requested_min_culmination
        return max(requested_min_culmination, self.min_culmination)

    @property
    def has_unlogged_status_change(self):
        """Returns whether the last log reflects the current station status"""
        last_log = StationStatusLog.objects.filter(station=self).order_by('-changed').first()

        if not last_log or (last_log.is_connected != self.is_connected or last_log.is_available
                            != self.is_available or last_log.testing != self.testing):
            return True
        return False

    # https://en.wikipedia.org/wiki/Maidenhead_Locator_System
    @property
    def qthlocator(self):
        """Returns the QTH locator for the station."""

        if self.lng is None or self.lat is None:
            return ''

        field_identifiers = [
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q',
            'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
        ]

        working_lon = (self.lng + 180) % 20
        lon_field = field_identifiers[int((self.lng + 180) / 20)]
        lon_square = int(working_lon / 2)
        working_lon = int((working_lon % 2) * 12)
        lon_subsquare = field_identifiers[working_lon]

        working_lat = (self.lat + 90) % 10
        lat_field = field_identifiers[int((self.lat + 90) / 10)]
        lat_square = int(working_lat)
        working_lat = int((working_lat - lat_square) * 24)
        lat_subsquare = field_identifiers[working_lat]

        # Combine all parts to form the QTH locator
        qthlocator = (
            f"{lon_field}{lat_field}{lon_square}{lat_square}"
            f"{lon_subsquare.lower()}{lat_subsquare.lower()}"
        )

        return qthlocator

    @property
    def active_configuration(self):
        """Returns the currently used configuration of the station"""
        try:
            conf = ActiveStationConfiguration.objects.get(station=self)
        except ActiveStationConfiguration.DoesNotExist:
            conf = None
        return conf

    def get_image(self):
        """Return the image of the station or the default image if there is a defined one"""
        if self.image and hasattr(self.image, 'url'):
            return self.image.url
        return settings.STATION_DEFAULT_IMAGE

    @property
    def is_connected(self) -> bool:
        """Returns whether the station has contacted Network recently"""
        try:
            heartbeat = self.last_seen + timedelta(minutes=int(settings.STATION_HEARTBEAT_TIME))
            return heartbeat > now()
        except TypeError:
            return False

    @property
    def has_location(self):
        """Return true if station location is defined"""
        if self.alt is None or self.lat is None or self.lng is None:
            return False
        return True

    @property
    def status_label(self):
        """Returns a text label that summarizes the station status"""
        if self.is_connected:
            if self.is_available:
                if self.testing:
                    return 'Testing'
                return 'Connected'
            return 'Unavailable'
        return 'Disconnected'

    @property
    def success_rate(self):
        """Return the success rate of the station - successful observation over failed ones"""
        rate = cache.get('station-{0}-rate'.format(self.id))
        if not rate:
            observations = self.observations.exclude(experimental=True
                                                     ).exclude(status__range=(0, 99))
            stats = observations.aggregate(
                bad=Count('pk', filter=Q(status__range=(-100, -1))),
                good=Count('pk', filter=Q(status__gte=100)),
                failed=Count('pk', filter=Q(status__lt=100))
            )
            good_count = stats['good'] or 0
            bad_count = stats['bad'] or 0
            failed_count = stats['failed'] or 0
            total = good_count + bad_count + failed_count
            if total:
                rate = int(100 * ((bad_count + good_count) / total))
                cache.set('station-{0}-rate'.format(self.id), rate, 60 * 60 * 6)
            else:
                rate = False
        return rate

    def __str__(self):
        if self.pk:
            return "%d - %s" % (self.pk, self.name)
        return "%s" % (self.name)

    @property
    def observations_stats(self):
        """ Return and objects with total and future observations of the station.
           For the total we cache the results for 6 hours and for future observations for 1 hour.
       """
        total_counter = cache.get('station-{0}-obs-total-stats'.format(self.id))
        if total_counter is None:
            total_counter = self.observations.count()
            cache.set('station-{0}-obs-total-stats'.format(self.id), total_counter, 60 * 60 * 6)

        future_counter = cache.get('station-{0}-obs-future-stats'.format(self.id))
        if future_counter is None:
            future_counter = self.observations.filter(end__gt=now()).count()
            cache.set('station-{0}-obs-future-stats'.format(self.id), future_counter, 60 * 60)

        return {'total': total_counter, 'future': future_counter}

    def clean(self):
        if re.search('[^\x20-\x7E\xA0-\xFF]', self.name, re.IGNORECASE):
            raise ValidationError(
                {
                    'name': (
                        'Please use characters that belong to ISO-8859-1'
                        ' (https://en.wikipedia.org/wiki/ISO/IEC_8859-1).'
                    )
                }
            )
        if re.search('[^\n\r\t\x20-\x7E\xA0-\xFF]', self.description, re.IGNORECASE):
            raise ValidationError(
                {
                    'description': (
                        'Please use characters that belong to ISO-8859-1'
                        ' (https://en.wikipedia.org/wiki/ISO/IEC_8859-1).'
                    )
                }
            )


class AntennaType(models.Model):
    """Model for antenna types."""
    name = models.CharField(max_length=25, unique=True)

    def __str__(self):
        return self.name


class Antenna(models.Model):
    """Model for antennas of SatNOGS ground stations."""
    antenna_type = models.ForeignKey(
        AntennaType, on_delete=models.PROTECT, related_name='antennas'
    )
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='antennas')

    @property
    def bands(self):
        """Return comma separated string of the bands that the antenna works on"""
        bands = []
        for frequency_range in self.frequency_ranges.all():
            for band in bands_from_range(frequency_range.min_frequency,
                                         frequency_range.max_frequency):
                if band not in bands:
                    bands.append(band)
        return ', '.join(bands)

    def __str__(self):
        if self.pk:
            return "%d - %s (#%s)" % (self.pk, self.antenna_type.name, self.station.id)
        if self.station.id:
            return "%s (#%s)" % (self.antenna_type.name, self.station.id)
        return "%s" % (self.antenna_type.name)


class FrequencyRange(models.Model):
    """Model for frequency ranges of antennas."""
    antenna = models.ForeignKey(Antenna, on_delete=models.CASCADE, related_name='frequency_ranges')
    min_frequency = models.BigIntegerField()
    max_frequency = models.BigIntegerField()

    @property
    def bands(self):
        """Return comma separated string of the bands that of the frequeny range"""
        bands = bands_from_range(self.min_frequency, self.max_frequency)
        return ', '.join(bands)

    class Meta:
        ordering = ['min_frequency']

    def clean(self):
        if self.max_frequency < self.min_frequency:
            raise ValidationError(
                {
                    'min_frequency': (
                        'Minimum frequency is greater than the maximum one ({0} > {1}).'.format(
                            self.min_frequency, self.max_frequency
                        )
                    ),
                    'max_frequency': (
                        'Maximum frequency is less than the minimum one ({0} < {1}).'.format(
                            self.max_frequency, self.min_frequency
                        )
                    ),
                }
            )
        if self.min_frequency < settings.MIN_FREQUENCY_FOR_RANGE:
            raise ValidationError(
                {
                    'min_frequency': ('Minimum frequency should be more than {0}.').format(
                        settings.MIN_FREQUENCY_FOR_RANGE
                    )
                }
            )
        if self.max_frequency > settings.MAX_FREQUENCY_FOR_RANGE:
            raise ValidationError(
                {
                    'max_frequency': ('Maximum frequency should be less than {0}.').format(
                        settings.MAX_FREQUENCY_FOR_RANGE
                    )
                }
            )


class StationStatusLog(models.Model):
    """Model for keeping Status log for Station."""
    station = models.ForeignKey(
        Station, related_name='station_logs', on_delete=models.CASCADE, null=True, blank=True
    )
    is_connected = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    testing = models.BooleanField(default=False)
    changed = models.DateTimeField(auto_now_add=True)

    @property
    def status_label(self):
        """Returns a text label that summarizes the station status"""
        if self.is_connected:
            if self.is_available:
                if self.testing:
                    return 'Testing'
                return 'Connected'
            return 'Unavailable'
        return 'Disconnected'

    @classmethod
    def create_from_station(cls, station):
        """
        Creates a StationStatusLog entry based on a given Station instance.
        """
        return cls.objects.create(
            station=station,
            testing=station.testing,
            is_available=station.is_available,
            is_connected=station.is_connected
        )

    class Meta:
        ordering = ['-changed']
        indexes = [
            models.Index(fields=["station", "-changed"]),
        ]

    def __str__(self):
        return '{0} - {1}'.format(self.station, self.status_label)


class StationUnavailabilityPeriod(models.Model):
    """Model for scheduled unavailability periods of a Station.

    During such a period the station is considered unavailable for scheduling.
    """
    station = models.ForeignKey(
        Station, related_name='unavailable_periods', on_delete=models.CASCADE
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start']
        indexes = [
            models.Index(fields=['station', 'start', 'end'], name='base_unavail_period_idx'),
        ]

    def clean(self):
        """Validates that the period's end is after its start"""
        super().clean()
        if self.start and self.end and self.start >= self.end:
            raise ValidationError({'end': 'End datetime should be after start datetime.'})

    def __str__(self):
        return '{0}: {1} - {2}'.format(self.station, self.start, self.end)


class Observation(models.Model):
    """Model for SatNOGS observations."""
    sat_id = models.CharField(db_index=True, max_length=24)
    tle_line_0 = models.CharField(
        max_length=69, blank=True, validators=[MinLengthValidator(1),
                                               MaxLengthValidator(69)]
    )
    tle_line_1 = models.CharField(
        max_length=69, blank=True, validators=[MinLengthValidator(69),
                                               MaxLengthValidator(69)]
    )
    tle_line_2 = models.CharField(
        max_length=69, blank=True, validators=[MinLengthValidator(69),
                                               MaxLengthValidator(69)]
    )
    tle_source = models.CharField(max_length=300, blank=True)
    tle_updated = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(
        User, related_name='observations', on_delete=models.SET_NULL, null=True, blank=True
    )
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField(db_index=True)
    ground_station = models.ForeignKey(
        Station, related_name='observations', on_delete=models.SET_NULL, null=True, blank=True
    )
    client_version = models.CharField(max_length=255, blank=True)
    client_metadata = models.TextField(blank=True)
    payload = models.FileField(
        upload_to=_name_observation_data, storage=_select_audio_storage, blank=True
    )
    waterfall = models.ImageField(
        upload_to=_name_observation_data, storage=_select_waterfall_storage, blank=True
    )
    """
    Meaning of values:
    True -> Waterfall has signal of the observed satellite (with-signal)
    False -> Waterfall has not signal of the observed satellite (without-signal)
    None -> Uknown whether waterfall has or hasn't signal of the observed satellite (unknown)
    """
    # old fields
    waterfall_status = models.BooleanField(blank=True, null=True, default=None)
    waterfall_status_datetime = models.DateTimeField(null=True, blank=True)
    waterfall_status_user = models.ForeignKey(
        User, related_name='waterfalls_vetted', on_delete=models.SET_NULL, null=True, blank=True
    )
    """
    Meaning of values:
    x < -100      -> Failed
    -100 =< x < 0 -> Bad
    0 =< x < 100  -> Unknown (Future if observation not completed)
    100 =< x      -> Good
    """
    status = models.SmallIntegerField(default=0)
    experimental = models.BooleanField(default=False)
    rise_azimuth = models.FloatField(blank=True, null=True)
    max_altitude = models.FloatField(blank=True, null=True)
    set_azimuth = models.FloatField(blank=True, null=True)
    audio_zipped = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    archive_identifier = models.CharField(max_length=255, blank=True)
    archive_url = models.URLField(blank=True, null=True)
    transmitter_uuid = ShortUUIDField(auto=False, db_index=True)
    transmitter_description = models.TextField(default='')
    transmitter_type = models.CharField(
        choices=list(zip(TRANSMITTER_TYPE, TRANSMITTER_TYPE)),
        max_length=11,
        default='Transmitter'
    )
    transmitter_uplink_low = models.BigIntegerField(blank=True, null=True)
    transmitter_uplink_high = models.BigIntegerField(blank=True, null=True)
    transmitter_uplink_drift = models.IntegerField(blank=True, null=True)
    transmitter_downlink_low = models.BigIntegerField(blank=True, null=True)
    transmitter_downlink_high = models.BigIntegerField(blank=True, null=True)
    transmitter_downlink_drift = models.IntegerField(blank=True, null=True)
    transmitter_mode = models.CharField(max_length=25, blank=True, null=True)
    transmitter_invert = models.BooleanField(default=False)
    transmitter_baud = models.FloatField(validators=[MinValueValidator(0)], blank=True, null=True)
    transmitter_created = models.DateTimeField(default=now)
    transmitter_status = models.BooleanField(null=True, blank=True)
    transmitter_unconfirmed = models.BooleanField(blank=True, null=True)
    transmitter_parameters = models.JSONField(blank=True, null=True)
    station_alt = models.PositiveIntegerField(null=True, blank=True)
    station_lat = models.FloatField(
        validators=[MaxValueValidator(90), MinValueValidator(-90)], null=True, blank=True
    )
    station_lng = models.FloatField(
        validators=[MaxValueValidator(180), MinValueValidator(-180)], null=True, blank=True
    )
    station_antennas = models.TextField(null=True, blank=True)
    center_frequency = models.BigIntegerField(blank=True, null=True)

    objects = ObservationManager.as_manager()

    @property
    def is_past(self):
        """Return true if observation is in the past (end time is in the past)"""
        return self.end < now()

    @property
    def is_future(self):
        """Return true if observation is in the future (end time is in the future)"""
        return self.end > now()

    @property
    def is_started(self):
        """Return true if observation has started (start time is in the past)"""
        return self.start < now()

    # The values bellow are used as returned values in the API and for css rules in templates
    @property
    def status_badge(self):
        """Return badge for status field"""
        if self.is_future:
            return "future"
        if self.status < -100:
            return "failed"
        if -100 <= self.status < 0:
            return "bad"
        if 0 <= self.status < 100:
            return "unknown"
        return "good"

    # The values bellow are used as displayed values in templates
    @property
    def status_display(self):
        """Return display name for status field"""
        if self.is_future:
            return "Future"
        if self.status < -100:
            return "Failed"
        if -100 <= self.status < 0:
            return "Bad"
        if 0 <= self.status < 100:
            return "Unknown"
        return "Good"

    @property
    def waterfall_status_badge(self):
        """Return badge for waterfall_status field"""
        status_info = self.get_waterfall_status()
        status = status_info['status']

        if status == 'good':
            return 'with-signal'
        if status == 'bad':
            return 'without-signal'
        return 'unknown'

    @property
    def waterfall_status_display(self):
        """Return display name for waterfall_status field"""
        status_info = self.get_waterfall_status()
        status = status_info['status']

        if status == 'good':
            return 'With Signal'
        if status == 'bad':
            return 'Without Signal'
        return 'Unknown'

    @property
    def has_waterfall(self):
        """Run some checks on the waterfall for existence of data."""
        if self.waterfall:
            return True
        return False

    @property
    def has_audio(self):
        """Run some checks on the payload for existence of data."""
        if self.archive_url:
            return True
        if self.payload:
            return True
        return False

    @property
    def has_demoddata(self):
        """Check if the observation has Demod Data."""
        if self.demoddata.exists():
            return True
        return False

    @property
    def has_artifact(self):
        """Check if the observation has an associated artifact in satnogs-db."""
        try:
            artifact_metadata = get_artifact_metadata_by_observation_id(self.id)
        except DBConnectionError:
            return False

        return truth(artifact_metadata)

    @property
    def artifact_url(self):
        """Return url for the oberations artifact file (if it exists)"""
        try:
            artifact_metadata = get_artifact_metadata_by_observation_id(self.id)
        except DBConnectionError:
            return ''

        if not artifact_metadata:
            return ''
        return artifact_metadata[0]['artifact_file']

    @property
    def audio_url(self):
        """Return url for observation's audio file"""
        if self.has_audio:
            if self.archive_url:
                return self.archive_url
            return self.payload.url
        return ''

    @property
    def observation_frequency(self):
        """
        Return the observation frequency
        """
        frequency = self.center_frequency or self.transmitter_downlink_low
        frequency_drift = self.transmitter_downlink_drift
        if self.center_frequency or frequency_drift is None:
            return frequency
        return int(round(frequency + ((frequency * frequency_drift) / 1e9)))

    def get_waterfall_status(self):
        """Get waterfall status via majority voting."""
        vettings = self.artifact_vettings.filter(artifact_type='waterfall')

        if not vettings.exists():
            return {'status': 'unknown', 'user': None, 'datetime': None}

        good_count = vettings.filter(vetted_status='good').count()
        bad_count = vettings.filter(vetted_status='bad').count()
        unknown_count = vettings.filter(vetted_status='unknown').count()

        # Determine status by majority (ties go to bad)
        if good_count > bad_count and good_count > unknown_count:
            status = 'good'
        elif bad_count > good_count and bad_count > unknown_count:
            status = 'bad'
        elif unknown_count > good_count and unknown_count > bad_count:
            status = 'unknown'
        elif good_count == bad_count and good_count > unknown_count:
            status = 'bad'
        elif good_count == unknown_count and good_count > bad_count:
            status = 'unknown'
        elif bad_count == unknown_count and bad_count > good_count:
            status = 'bad'
        else:
            status = 'bad'

        latest = vettings.order_by('-vetted_datetime').first()

        return {'status': status, 'user': latest.user, 'datetime': latest.vetted_datetime}

    class Meta:
        ordering = ['-start', '-end']
        indexes = [models.Index(fields=['-start', '-end'])]
        permissions = (('can_vet', 'Can vet observations'), )

    def __str__(self):
        return str(self.id)

    def get_absolute_url(self):
        """Return absolute url of the model object"""
        return reverse('base:observation_view', kwargs={'observation_id': self.id})


@receiver(models.signals.post_delete, sender=Observation)
def observation_remove_files(sender, instance, **kwargs):  # pylint: disable=W0613
    """Remove audio and waterfall files of an observation if the observation is deleted"""
    if instance.payload:
        instance.payload.delete(save=False)
    if instance.waterfall:
        instance.waterfall.delete(save=False)


class ArtifactVetting(models.Model):
    """Model for individual vetting actions on observation artifacts."""

    # artifact types (extensible for future artifact types)
    ARTIFACT_TYPE = [
        ('waterfall', 'Waterfall'),
    ]

    VETTING_STATUS = [
        ('good', 'Good'),
        ('bad', 'Bad'),
        ('unknown', 'Unknown'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='artifact_vettings')
    observation = models.ForeignKey(
        'Observation', on_delete=models.CASCADE, related_name='artifact_vettings'
    )
    artifact_type = models.CharField(max_length=50, choices=ARTIFACT_TYPE, default='waterfall')

    vetted_status = models.CharField(max_length=20, choices=VETTING_STATUS)
    vetted_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Database indexes
        indexes = [
            models.Index(fields=['-vetted_datetime']),
        ]

        ordering = ['-vetted_datetime']
        unique_together = [['user', 'observation', 'artifact_type']]
        verbose_name = 'Artifact Vetting'

        # Permissions
        permissions = (('can_vet_artifacts', 'Can vet observation artifacts'), )

    def __str__(self):
        return (
            f"{self.user.username} "
            f"- Obs #{self.observation.id} - {self.artifact_type}: {self.vetted_status}"
        )


class DemodData(models.Model):
    """Model for DemodData."""
    observation = models.ForeignKey(
        Observation, related_name='demoddata', on_delete=models.CASCADE
    )
    demodulated_data = models.FileField(
        upload_to=_name_observation_demoddata, storage=_select_data_storage, blank=True
    )
    copied_to_db = models.BooleanField(default=False)
    is_image = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["copied_to_db", "is_image"])]

    def display_payload_hex(self):
        """
        Return the content of the data file as hex dump of the following form: `DE AD C0 DE`.
        """
        if self.demodulated_data:
            with self.demodulated_data.storage.open(self.demodulated_data.name,
                                                    mode='rb') as data_file:
                payload = data_file.read()

        return _decode_pretty_hex(payload)

    def display_payload_utf8(self):
        """
        Return the content of the data file decoded as UTF-8. If this fails,
        show as hex dump.
        """
        if self.demodulated_data:
            with self.demodulated_data.storage.open(self.demodulated_data.name,
                                                    mode='rb') as data_file:
                payload = data_file.read()

        try:
            return payload.decode('utf-8')
        except UnicodeDecodeError:
            return _decode_pretty_hex(payload)

    def __str__(self):
        return '{} - {}'.format(self.id, self.demodulated_data)


@receiver(models.signals.post_delete, sender=DemodData)
def demoddata_remove_files(sender, instance, **kwargs):  # pylint: disable=W0613
    """Remove data file of an observation if the observation is deleted"""
    if instance.demodulated_data:
        instance.demodulated_data.delete(save=False)
