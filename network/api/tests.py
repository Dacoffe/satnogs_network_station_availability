"""SatNOGS Network API test suites"""
import json
from datetime import timedelta

import pytest
from django.test import TestCase
from django.utils.timezone import now
from requests.utils import parse_header_links
from rest_framework import status
from rest_framework.utils.encoders import JSONEncoder

from network.api.pagination import ObservationCursorPagination
from network.base.tests import AntennaFactory, FrequencyRangeFactory, ObservationFactory, \
    SatelliteFactory, StationFactory


@pytest.mark.django_db(transaction=True)
class JobViewApiTest(TestCase):
    """
    Tests the Job View API
    """
    observation = None
    satellites = []
    stations = []

    def setUp(self):
        for _ in range(1, 10):
            self.satellites.append(SatelliteFactory())
        for _ in range(1, 10):
            self.stations.append(StationFactory())
        self.future_observation = ObservationFactory(start=now() + timedelta(days=1))
        self.past_observation = ObservationFactory(start=now() - timedelta(days=1))

    def test_job_view_api(self):
        """Test the Job View API"""
        response = self.client.get('/api/jobs/')
        response_json = json.loads(response.content)
        self.assertEqual(len(response_json), 1)
        self.assertEqual(response_json[0]['id'], self.future_observation.id)
        self.assertNotEqual(response_json[0]['id'], self.past_observation.id)


@pytest.mark.django_db(transaction=True)
class StationViewApiTest(TestCase):
    """
    Tests the Station View API
    """
    station = None

    def setUp(self):
        self.encoder = JSONEncoder()
        self.station = StationFactory()
        self.antenna = AntennaFactory(station=self.station)
        self.frequency_range = FrequencyRangeFactory(antenna=self.antenna)

    def test_station_view_api(self):
        """Test the Station View API"""

        antenna_types = {
            'Dipole': 'dipole',
            'V-Dipole': 'v-dipole',
            'Discone': 'discone',
            'Ground Plane': 'ground',
            'Yagi': 'yagi',
            'Cross Yagi': 'cross-yagi',
            'Helical': 'helical',
            'Parabolic': 'parabolic',
            'Vertical': 'vertical',
            'Turnstile': 'turnstile',
            'Quadrafilar': 'quadrafilar',
            'Eggbeater': 'eggbeater',
            'Lindenblad': 'lindenblad',
            'Parasitic Lindenblad': 'paralindy',
            'Patch': 'patch',
            'Other Directional': 'other direct',
            'Other Omni-Directional': 'other omni',
        }

        ser_ants = [
            {
                'band': self.frequency_range.bands,
                'frequency': self.frequency_range.min_frequency,
                'frequency_max': self.frequency_range.max_frequency,
                'antenna_type': antenna_types[self.antenna.antenna_type.name],
                'antenna_type_name': self.antenna.antenna_type.name,
            }
        ]

        station_serialized = {
            'id': self.station.id,
            'altitude': self.station.alt,
            'antenna': ser_ants,
            'client_version': self.station.client_version,
            'created': self.encoder.default(self.station.created),
            'description': self.station.description,
            'last_seen': self.encoder.default(self.station.last_seen),
            'lat': self.station.lat,
            'lng': self.station.lng,
            'min_horizon': self.station.horizon,
            'name': self.station.name,
            'observations': 0,
            'qthlocator': self.station.qthlocator,
            'target_utilization': self.station.target_utilization,
            'status': self.station.get_status_display(),
            'future_observations': 0,  # No observation scheduled in the test
            'image': self.station.get_image(),
            'success_rate': self.station.success_rate,
            'owner': self.station.owner.username
        }

        response = self.client.get('/api/stations/')
        response_json = json.loads(response.content)
        self.assertEqual(response_json, [station_serialized])


class ObservationViewApiTest(TestCase):
    """
    Tests the Observation API View
    """

    def setUp(self):
        self.observations = []
        for _ in range(ObservationCursorPagination.page_size * 2 + 1):
            self.observations.append(ObservationFactory())

    def test_observations_listview_pagination(self):
        """
        Tests the pagination of the observations list view
        """
        response = self.client.get('/api/observations/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == ObservationCursorPagination.page_size
        assert response.get('link')
        links = parse_header_links(response['link'])
        assert links
        next_link = next((link for link in links if link['rel'] == 'next'), None)
        assert next_link
        assert next_link.get('url')

        next_response = self.client.get(next_link['url'])
        assert next_response.status_code == status.HTTP_200_OK
        data = next_response.json()
        assert len(data) == ObservationCursorPagination.page_size
        links = parse_header_links(next_response['link'])
        assert links
        prev_link = next((link for link in links if link['rel'] == 'prev'), None)
        assert prev_link
        assert prev_link.get('url')
        assert self.client.get(prev_link['url']).status_code == status.HTTP_200_OK

        next_link = next((link for link in links if link['rel'] == 'next'), None)
        assert next_link
        assert next_link.get('url')
        assert self.client.get(next_link['url']).status_code == status.HTTP_200_OK
