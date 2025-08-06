"""SatNOGS Network base test suites"""
# pylint: disable=too-few-public-methods, redefined-outer-name
import random
from datetime import datetime, timedelta

import factory
import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.cache import cache
from django.db import transaction
from django.test import Client, TestCase
from django.utils.timezone import now
# C0412 below clashes with isort
from factory import fuzzy  # pylint: disable=C0412

from network.base.cache import get_satellites
from network.base.models import Antenna, AntennaType, DemodData, FrequencyRange, Observation, \
    Station, StationConfiguration, StationConfigurationSchema
from network.base.perms import has_delete_obs_perms, has_perm_to_schedule_on_station, \
    has_schedule_perms, has_vet_perms
from network.base.test_orbital import generate_fake_tle
from network.users.models import User
from network.users.tests import UserFactory


def generate_payload():
    """Create data payloads"""
    payload = '{0:b}'.format(random.randint(500000000, 510000000))
    digits = 1824
    while digits:
        digit = random.randint(0, 1)
        payload += str(digit)
        digits -= 1
    return payload


def generate_payload_name():
    """Create payload names"""
    filename = datetime.strftime(
        fuzzy.FuzzyDateTime(now() - timedelta(days=10), now()).fuzz(), '%Y%m%dT%H%M%SZ'
    )
    return filename


class StationFactory(factory.django.DjangoModelFactory):
    """Station model factory."""
    owner = factory.SubFactory(UserFactory)
    name = fuzzy.FuzzyText()
    image = factory.django.ImageField()
    alt = fuzzy.FuzzyInteger(0, 800)
    lat = fuzzy.FuzzyFloat(-20, 70)
    lng = fuzzy.FuzzyFloat(-180, 180)
    featured_date = fuzzy.FuzzyDateTime(now() - timedelta(days=10), now())
    is_available = fuzzy.FuzzyChoice(choices=[True, False])
    testing = fuzzy.FuzzyChoice(choices=[True, False])
    last_seen = fuzzy.FuzzyDateTime(now() - timedelta(days=3), now())
    horizon = fuzzy.FuzzyInteger(10, 20)

    @factory.post_generation
    def create_configuration(self, create, *args, **kwargs):
        """Create and assign a configuration for the station"""
        if not create:
            return

        StationConfigurationFactory(
            station=self, schema=StationConfigurationSchema.objects.get(pk=1)
        )

    class Meta:
        model = Station


class StationConfigurationFactory(factory.django.DjangoModelFactory):
    """Station configuration model factory."""

    class Meta:
        model = StationConfiguration

    station = factory.Iterator(Station.objects.all())
    schema = factory.Iterator(StationConfigurationSchema.objects.all())
    name = fuzzy.FuzzyText()


class AntennaFactory(factory.django.DjangoModelFactory):
    """Antenna model factory."""
    antenna_type = factory.Iterator(AntennaType.objects.all())
    station = factory.Iterator(Station.objects.all())

    class Meta:
        model = Antenna


class FrequencyRangeFactory(factory.django.DjangoModelFactory):
    """FrequencyRange model factory."""
    min_frequency = fuzzy.FuzzyInteger(200000000, 500000000)
    max_frequency = fuzzy.FuzzyInteger(500000000, 800000000)
    antenna = factory.Iterator(Antenna.objects.all())

    class Meta:
        model = FrequencyRange


def create_satellite():
    """Adds a new satellite to cache and returns it."""
    sats = get_satellites()

    # This function is used when testing but also by the 'initialize' management command.
    # When it is used by 'initialize', we want actual sat_id values.
    # When testing, satellite data from satnogs-db is not available so we mock them.
    sat_id = fuzzy.FuzzyText(
        length=24
    ).fuzz() if settings.TESTING else fuzzy.FuzzyChoice(list(sats.keys())).fuzz()
    sat = {
        'sat_id': sat_id,
        'name': fuzzy.FuzzyText().fuzz(),
        'norad_cat_id': fuzzy.FuzzyInteger(2000, 4000).fuzz()
    }
    sats[sat['sat_id']] = sat
    cache.set('satellites', sats)
    return sat


def fuzzy_sat_id():
    """Returns the sat_id of a satellite, that has been added to cache."""
    return create_satellite()['sat_id']


class ObservationFactory(factory.django.DjangoModelFactory):  # pylint: disable=R0902
    """Observation model factory."""
    sat_id = factory.LazyFunction(fuzzy_sat_id)
    author = factory.SubFactory(UserFactory)
    start = fuzzy.FuzzyDateTime(
        now() - timedelta(days=3), now() + timedelta(days=3), force_microsecond=0
    )
    end = factory.LazyAttribute(lambda x: x.start + timedelta(minutes=random.randint(5, 12)))
    ground_station = factory.SubFactory(StationFactory)
    tle_line_0 = ''
    tle_line_1 = ''
    tle_line_2 = ''
    tle_source = ''
    tle_updated = None
    payload = factory.django.FileField(filename='data.ogg')
    waterfall_status_datetime = factory.LazyAttribute(
        lambda x: x.end + timedelta(hours=random.randint(1, 20))
    )
    waterfall_status_user = factory.SubFactory(UserFactory)
    waterfall_status = fuzzy.FuzzyChoice(choices=[None, True, False])
    status = fuzzy.FuzzyInteger(-1000, 1000, step=10)
    transmitter_uuid = fuzzy.FuzzyText(length=20)
    transmitter_description = fuzzy.FuzzyText()
    transmitter_uplink_low = fuzzy.FuzzyInteger(200000000, 500000000, step=10000)
    transmitter_uplink_high = fuzzy.FuzzyInteger(200000000, 500000000, step=10000)
    transmitter_downlink_low = fuzzy.FuzzyInteger(200000000, 500000000, step=10000)
    transmitter_downlink_high = fuzzy.FuzzyInteger(200000000, 500000000, step=10000)
    transmitter_mode = fuzzy.FuzzyText(length=10)
    transmitter_invert = fuzzy.FuzzyChoice(choices=[True, False])
    transmitter_baud = fuzzy.FuzzyInteger(4000, 22000, step=1000)
    transmitter_created = fuzzy.FuzzyDateTime(
        now() - timedelta(days=100),
        now() - timedelta(days=3)
    )

    @factory.post_generation
    def generate_tle(obj, create, extracted, **kwargs):  # pylint: disable=W0613
        "Generate TLE set based on station location and start time of observation"
        date = obj.start + (obj.end - obj.start) / 2
        tle = generate_fake_tle(
            obj.ground_station.lat, obj.ground_station.lng, obj.ground_station.alt, date
        )
        obj.tle_line_0 = tle[0].strip()
        obj.tle_line_1 = tle[1]
        obj.tle_line_2 = tle[2]
        obj.tle_source = 'fake tle'
        obj.tle_updated = obj.start - timedelta(hours=5)

    class Meta:
        model = Observation


class RealisticObservationFactory(ObservationFactory):
    """Observation model factory which uses existing satellites and tles."""
    author = factory.Iterator(User.objects.all())
    ground_station = factory.Iterator(Station.objects.all())
    waterfall_status_user = factory.Iterator(User.objects.all())


class DemodDataFactory(factory.django.DjangoModelFactory):
    """DemodData model factory."""
    observation = factory.Iterator(Observation.objects.all())
    demodulated_data = factory.django.FileField()

    class Meta:
        model = DemodData


@pytest.mark.django_db()
class HomeViewTest(TestCase):
    """
    Simple test to make sure the home page is working
    """

    def test_home_page(self):
        """Test for string in home page"""
        response = self.client.get('/')
        self.assertContains(response, 'Crowd-sourced satellite operations')


@pytest.mark.django_db()
class AboutViewTest(TestCase):
    """
    Simple test to make sure the about page is working
    """

    def test_about_page(self):
        """Test for string in about page"""
        response = self.client.get('/about/')
        self.assertContains(response, 'SatNOGS Network is a global management interface')


@pytest.mark.django_db
class StationListViewTest(TestCase):
    """
    Test to ensure the station list is generated by Django
    """
    client = Client()
    stations = []

    def setUp(self):
        for _ in range(1, 10):
            self.stations.append(StationFactory())

    def test_station_list(self):
        """Test for owners and station names in station page"""
        response = self.client.get('/stations/')
        for station in self.stations:
            self.assertContains(response, station.owner)
            self.assertContains(response, station.name)


@pytest.mark.django_db()
class ObservationsListViewTest(TestCase):
    """
    Test to ensure the observation list is generated by Django
    """
    client = Client()
    observations = []
    satellites = []
    stations = []

    def setUp(self):
        # Clear the data and create some new random data
        with transaction.atomic():
            Observation.objects.all().delete()
        self.satellites = []
        self.observations_bad = []
        self.observations_good = []
        self.observations_unknown = []
        self.observations = []
        with transaction.atomic():
            for _ in range(1, 10):
                self.satellites.append(create_satellite())
            for _ in range(1, 10):
                self.stations.append(StationFactory())
            for i in range(1, 5):
                obs = ObservationFactory(status=-100, start=now() - timedelta(days=i))
                self.observations_bad.append(obs)
                self.observations.append(obs)
            for i in range(1, 5):
                obs = ObservationFactory(status=100, start=now() - timedelta(days=i))
                self.observations_good.append(obs)
                self.observations.append(obs)
            for _ in range(1, 5):
                obs = ObservationFactory(status=0)
                self.observations_unknown.append(obs)
                self.observations.append(obs)

    def test_observations_list(self):
        """Test for transmitter modes of each observation in observations page"""
        response = self.client.get('/observations/')
        for observation in self.observations:
            if observation.start > now() - timedelta(days=1):
                self.assertContains(response, observation.transmitter_mode)

    def test_observations_list_select_bad(self):
        """Test for transmitter modes of each bad observation in observations page"""
        response = self.client.get('/observations/?future=0&good=0&unknown=0&failed=0')

        for observation in self.observations_bad:
            self.assertContains(response, observation.transmitter_mode)

    def test_observations_list_select_good(self):
        """Test for transmitter modes of each good observation in observations page"""
        response = self.client.get('/observations/?future=0&bad=0&unknown=0&failed=0')

        for observation in self.observations_good:
            self.assertContains(response, observation.transmitter_mode)

    def test_observations_list_select_unknown(self):
        """Test for transmitter modes of each unknown observation in observations page"""
        response = self.client.get('/observations/?bad=0&good=0&failed=0')

        for observation in self.observations_unknown:
            self.assertContains(response, observation.transmitter_mode)


class NotFoundErrorTest(TestCase):
    """
    Test the 404 not found handler
    """
    client = Client()

    def test_404_not_found(self):
        """Test for "404" html status code in response for requesting a non-existed page"""
        response = self.client.get('/blah')
        self.assertEqual(response.status_code, 404)


class RobotsViewTest(TestCase):
    """
    Test the robots.txt handler
    """
    client = Client()

    def test_robots(self):
        """Test for "Disallow" string in response for requesting robots.txt"""
        response = self.client.get('/robots.txt')
        self.assertContains(response, 'Disallow: /')


@pytest.mark.django_db()
class ObservationViewTest(TestCase):
    """
    Test to ensure the observation list is generated by Django
    """
    client = Client()
    observation = None
    satellites = []
    stations = []
    user = None

    def setUp(self):
        self.user = UserFactory()
        moderators = Group.objects.get(name='Moderators')
        moderators.user_set.add(self.user)
        for _ in range(1, 10):
            self.satellites.append(create_satellite())
        for _ in range(1, 10):
            self.stations.append(StationFactory())
        self.observation = ObservationFactory()

    def test_observation(self):
        """Test for observer and transmitter mode in observation page"""
        response = self.client.get('/observations/%d/' % self.observation.id)
        self.assertContains(response, self.observation.author.username)
        self.assertContains(response, self.observation.transmitter_mode)


@pytest.mark.django_db()
class StationViewTest(TestCase):
    """
    Test to ensure the observation list is generated by Django
    """
    client = Client()
    station = None

    def setUp(self):
        self.station = StationFactory()

    def test_observation(self):
        """Test for owner, elevation and min horizon in station page"""
        response = self.client.get('/stations/%d/' % self.station.id)
        self.assertContains(response, self.station.owner.username)
        self.assertContains(response, self.station.alt)
        self.assertContains(response, self.station.horizon)


@pytest.mark.django_db()
class StationDeleteTest(TestCase):
    """
    Test to ensure the observation list is generated by Django
    """
    client = Client()
    station = None
    user = None

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.station = StationFactory()
        self.station.owner = self.user
        self.station.save()

    def test_station_delete(self):
        """Test deletion of station"""
        response = self.client.get('/stations/%d/delete/' % self.station.id)
        self.assertRedirects(response, '/users/%s/' % self.user.username)
        with self.assertRaises(Station.DoesNotExist):
            _lookup = Station.objects.get(pk=self.station.id)  # noqa:F841


@pytest.mark.django_db()
class SettingsSiteViewTest(TestCase):
    """
    Test to ensure the satellite fetch feature works
    """
    client = Client()
    user = None

    def setUp(self):
        self.user = UserFactory()
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)

    def test_get(self):
        """Test for "Fetch Data" in Settings Site page"""
        response = self.client.get('/settings_site/')
        self.assertContains(response, 'Fetch Data')


@pytest.mark.django_db()
class ObservationModelTest(TestCase):
    """
    Test various properties of the Observation Model
    """
    observation = None
    satellites = []
    user = None
    admin = None

    def setUp(self):
        for _ in range(1, 10):
            self.satellites.append(create_satellite())
        self.observation = ObservationFactory()
        self.observation.end = now()
        self.observation.save()

    def test_is_passed(self):
        """Test for observation be in past"""
        self.assertTrue(self.observation.is_past)


@pytest.mark.django_db()
def test_connected_stations_only_returns_connected_owned_stations():
    """Tests the property user.connected_stations"""
    user = UserFactory()
    StationFactory(owner=user, last_seen=now())
    StationFactory(owner=user, last_seen=now() - timedelta(days=10))
    StationFactory(owner=UserFactory(), last_seen=now())

    connected = user.connected_stations
    assert all(s.owner == user and s.is_connected for s in connected)


@pytest.mark.django_db()
def test_useable_stations_filter_correctly():
    """Tests the property user.useable_stations"""
    user = UserFactory()
    StationFactory(owner=user, last_seen=now(), is_available=True, lat=0.0, lng=0.0, alt=0.0)
    StationFactory(owner=user, last_seen=now(), is_available=False, lat=0.0, lng=0.0, alt=0.0)
    StationFactory(owner=user, last_seen=now(), is_available=True, lat=None, lng=0.0, alt=0.0)

    useable = user.useable_stations
    assert useable.count() == 1


@pytest.fixture
def setup_user_with_role(db):  # pylint: disable=unused-argument
    """Creates users with different attributes to facilitate testing cases"""

    def _make_user_from_case(case):
        if not case.get("is_authenticated", True):
            return AnonymousUser()

        user = UserFactory(is_superuser=case.get("is_superuser", False))

        for group_name in case.get("groups", []):
            group, _ = Group.objects.get_or_create(name=group_name)
            group.user_set.add(user)

        for perm in case.get("permissions", []):
            app_label, codename = perm.split('.', 1)
            permission = Permission.objects.get(
                content_type__app_label=app_label, codename=codename
            )
            user.user_permissions.add(permission)

        station_statuses = dict(case.get("own_station_statuses", {}))
        # If the dict is not empty, the user is considered a station owner
        if station_statuses:
            connected = station_statuses.pop("connected", None)

            if connected is None:
                station_statuses["last_seen"] = None
            elif not connected:
                station_statuses["last_seen"] = now() - timedelta(days=3)
            else:
                station_statuses["last_seen"] = now()

            StationFactory(owner=user, **station_statuses)

        return user

    return _make_user_from_case


test_cases_user_can_schedule_on_station = [
    {
        "description": "non-authenticated user",
        'is_authenticated': False,
        "scheduling_own_station": False,
        "expected": False,
    },
    {
        "description": "authenticated user",
        "scheduling_own_station": False,
        "expected": False,
    },
    {
        "description": "station owner with disconnected station",
        "own_station_statuses": {
            "connected": False,
            "is_available": True,
        },
        "scheduling_own_station": False,
        "expected": False,
    },
    {
        "description": "station owner with unavailable station",
        "own_station_statuses": {
            "connected": True,
            "is_available": False,
        },
        "scheduling_own_station": False,
        "expected": False,
    },
    {
        "description": "station owner with unavailable station on own",
        "own_station_statuses": {
            "connected": True,
            "is_available": False,
        },
        "scheduling_own_station": True,
        "expected": True,
    },
    {
        "description": "station owner with testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": True,
        },
        "scheduling_own_station": False,
        "expected": False,
    },
    {
        "description": "station owner with testing station on own",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": True,
        },
        "scheduling_own_station": True,
        "expected": True,
    },
    {
        "description": "station owner with non-testing available station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": False,
        },
        "scheduling_own_station": False,
        "expected": True,
    },
    {
        "description": "operator on available",
        "groups": ['Operators'],
        "scheduling_own_station": False,
        'is_target_station_available': True,
        "expected": True,
    },
    {
        "description": "operator on unavailable",
        "groups": ['Operators'],
        "scheduling_own_station": False,
        'is_target_station_available': False,
        "expected": False,
    },
    {
        "description": "moderator on unavailable",
        "groups": ['Moderators'],
        "scheduling_own_station": False,
        'is_target_station_available': False,
        "expected": True,
    },
    {
        "description": "superuser on unavailable",
        "is_superuser": True,
        "scheduling_own_station": False,
        'is_target_station_available': False,
        "expected": True,
    },
]


@pytest.mark.parametrize(
    "case", test_cases_user_can_schedule_on_station, ids=lambda case: case["description"]
)
def test_user_can_schedule_on_station(setup_user_with_role, case):
    """Tests which kinds of users have permission to schedule on different kinds of stations"""
    user = setup_user_with_role(case)

    owner = user if case.get("scheduling_own_station", False) else UserFactory()
    station = StationFactory(
        owner=owner, is_available=case.get("is_target_station_available", True)
    )

    assert has_perm_to_schedule_on_station(user, station) is case["expected"]


test_cases_user_can_schedule = [
    {
        "description": "non-authenticated user",
        'is_authenticated': False,
        "expected": False,
    },
    {
        "description": "authenticated user",
        "expected": False,
    },
    {
        "description": "station owner of disconnected station",
        "own_station_statuses": {
            "connected": False
        },
        "expected": False,
    },
    {
        "description": "station owner of disconnected station",
        "own_station_statuses": {
            "connected": True,
            "is_available": False
        },
        "expected": True,
    },
    {
        "description": "station owner of disconnected station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": True,
        },
        "expected": True,
    },
    {
        "description": "operator",
        "groups": ['Operators'],
        "expected": True,
    },
    {
        "description": "moderator",
        "groups": ['Moderators'],
        "expected": True,
    },
    {
        "description": "superuser",
        "is_superuser": True,
        "expected": True,
    },
]


@pytest.mark.parametrize(
    'case', test_cases_user_can_schedule, ids=lambda case: case["description"]
)
def test_user_can_schedule(setup_user_with_role, case):
    """
    Tests which kinds of users have permission to schedule
    (used to display the scheduling page)
    """
    user = setup_user_with_role(case)
    assert has_schedule_perms(user) is case['expected']


test_cases_has_vet_perms = [
    {
        "description": "non-authenticated user",
        'is_authenticated': False,
        "expected": False,
    },
    {
        "description": "authenticated user",
        "expected": False,
    },
    {
        "description": "author station owner of never connected (future) station",
        "own_station_statuses": {
            "connected": None
        },
        "is_author": True,
        "expected": False,
    },
    {
        "description": "author station owner of disconnected station",
        "own_station_statuses": {
            "connected": False
        },
        "is_author": True,
        "expected": True,
    },
    {
        "description": "station owner of disconnected station on own",
        "own_station_statuses": {
            "connected": False
        },
        "scheduling_own_station": True,
        "expected": True,
    },
    {
        "description": "station owner of disconnected station (not author or owner)",
        "own_station_statuses": {
            "connected": False
        },
        "expected": False,
    },
    {
        "description": "station owner of unavailable, non-testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": False,
            "testing": False
        },
        "expected": False,
    },
    {
        "description": "author station owner of unavailable, non-testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": False,
            "testing": False
        },
        "is_author": True,
        "expected": True,
    },
    {
        "description": "station owner of unavailable, non-testing station on own",
        "own_station_statuses": {
            "connected": True,
            "is_available": False,
            "testing": False
        },
        "scheduling_own_station": True,
        "expected": True,
    },
    {
        "description": "station owner of available, testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": True
        },
        "expected": False,
    },
    {
        "description": "author station owner of available, testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": True
        },
        "is_author": True,
        "expected": True,
    },
    {
        "description": "station owner of available, testing station on own",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": True
        },
        "scheduling_own_station": True,
        "expected": True,
    },
    {
        "description": "station owner of available, non-testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": False
        },
        "expected": True,
    },
    {
        "description": "has can_vet perm",
        "permissions": ["base.can_vet"],
        "expected": True,
    },
    {
        "description": "operator",
        "groups": ["Operators"],
        "expected": True,
    },
    {
        "description": "moderator",
        "groups": ["Moderators"],
        "expected": True,
    },
    {
        "description": "admin",
        "is_superuser": True,
        "expected": True,
    },
]


@pytest.mark.parametrize('case', test_cases_has_vet_perms, ids=lambda case: case["description"])
def test_has_vet_perms(setup_user_with_role, case):
    """Tests which kinds of users can vet different kinds of observations"""
    user = setup_user_with_role(case)

    kwargs = {}
    if case.get('is_author', False):
        kwargs["author"] = user
    if case.get('scheduling_own_station', False):
        kwargs["ground_station"] = user.ground_stations.first()

    observation = ObservationFactory(**kwargs)

    assert has_vet_perms(user, observation) is case['expected']


test_cases_can_delete_obs = [
    {
        "description": "non-authenticated user",
        'is_authenticated': False,
        "expected": False,
    },
    {
        "description": "authenticated user",
        "expected": False,
    },
    {
        "description": "station owner of disconnected unavailable testing station on own",
        "own_station_statuses": {
            "connected": False,
            "is_available": False,
            "testing": True
        },
        "scheduling_own_station": True,
        "expected": True,
    },
    {
        "description": "author station owner of disconnected unavailable testing station",
        "own_station_statuses": {
            "connected": False,
            "is_available": False,
            "testing": True
        },
        "is_author": True,
        "expected": True,
    },
    {
        "description": "operator station owner of connected available non-testing station",
        "own_station_statuses": {
            "connected": True,
            "is_available": True,
            "testing": False
        },
        "groups": ["Operators"],
        "expected": False,
    },
    {
        "description": "moderator",
        "groups": ["Moderators"],
        "expected": True,
    },
    {
        "description": "admin",
        "is_superuser": True,
        "expected": True,
    },
    {
        "description": "admin on old observation",
        "is_superuser": True,
        "is_future": False,
        "expected": False,
    },
]


@pytest.mark.parametrize('case', test_cases_can_delete_obs, ids=lambda case: case["description"])
def test_can_delete_obs(setup_user_with_role, case):
    """Tests which kinds of users can delete different kinds of observations"""
    user = setup_user_with_role(case)

    kwargs = {}
    if case.get('is_author', False):
        kwargs["author"] = user
    if case.get('scheduling_own_station', False):
        kwargs["ground_station"] = user.ground_stations.first()
    if case.get('is_future', True):
        kwargs["start"] = fuzzy.FuzzyDateTime(
            now() + timedelta(minutes=1), now() + timedelta(days=3), force_microsecond=0
        )
    else:
        kwargs["start"] = fuzzy.FuzzyDateTime(
            now() - timedelta(days=3), now() - timedelta(minutes=1), force_microsecond=0
        )

    observation = ObservationFactory(**kwargs)

    assert has_delete_obs_perms(user, observation) is case['expected']
