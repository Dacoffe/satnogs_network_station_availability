"""SatNOGS Network django rest framework Filters class"""
from datetime import timedelta

import django_filters
from django import forms
from django.conf import settings
from django.db.models import Q
from django.utils.timezone import now
from django_filters.rest_framework import FilterSet

from network.base.cache import get_satellite_by_norad
from network.base.models import Observation, Station
from network.users.models import User


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    """Filter for comma separated numbers"""


class ObservationViewFilter(FilterSet):
    """SatNOGS Network Observation API View Filter"""
    OBSERVATION_STATUS_CHOICES = [
        ('failed', 'Failed'),
        ('bad', 'Bad'),
        ('unknown', 'Unknown'),
        ('future', 'Future'),
        ('good', 'Good'),
    ]

    WATERFALL_STATUS_CHOICES = [
        (1, 'With Signal'),
        (0, 'Without Signal'),
    ]

    start = django_filters.IsoDateTimeFilter(field_name='start', lookup_expr='gte')
    start__lt = django_filters.IsoDateTimeFilter(field_name='start', lookup_expr='lt')
    end = django_filters.IsoDateTimeFilter(field_name='end', lookup_expr='lte')
    end__gt = django_filters.IsoDateTimeFilter(field_name='end', lookup_expr='gt')
    status = django_filters.ChoiceFilter(
        field_name='status', choices=OBSERVATION_STATUS_CHOICES, method='filter_status'
    )
    waterfall_status = django_filters.ChoiceFilter(
        field_name='waterfall_status', choices=WATERFALL_STATUS_CHOICES, null_label='Unknown'
    )
    vetted_user = django_filters.ModelChoiceFilter(
        label='Vetted user (deprecated: will be removed in next version)',
        field_name='waterfall_status_user',
        queryset=User.objects.all()
    )

    observer = django_filters.ModelChoiceFilter(
        label="observer",
        field_name='author',
        queryset=User.objects.filter(observations__isnull=False).distinct()
    )

    observation_id = NumberInFilter(field_name='id', label="Observation ID(s)")

    norad_cat_id = django_filters.NumberFilter(label="Norad ID", method='filter_by_norad_cat_id')

    def filter_by_norad_cat_id(self, queryset, name, value):  # pylint: disable=W0613
        """
        Filters by norad_cat_id using the satellite cache.
        """

        sat = get_satellite_by_norad(int(value))

        if sat:
            return queryset.filter(sat_id=sat['sat_id'])

        return queryset.none()

    # see https://django-filter.readthedocs.io/en/master/ref/filters.html for W0613
    def filter_status(self, queryset, name, value):  # pylint: disable=W0613
        """ Returns filtered observations for a given observation status"""
        if value == 'failed':
            observations = queryset.filter(status__lt=-100)
        if value == 'bad':
            observations = queryset.filter(status__range=(-100, -1))
        if value == 'unknown':
            observations = queryset.filter(status__range=(0, 99), end__lte=now())
        if value == 'future':
            observations = queryset.filter(end__gt=now())
        if value == 'good':
            observations = queryset.filter(status__gte=100)
        return observations

    class Meta:
        model = Observation
        fields = [
            'id', 'status', 'ground_station', 'start', 'end', 'transmitter_uuid',
            'transmitter_mode', 'transmitter_type', 'waterfall_status', 'vetted_user', 'observer',
            'sat_id'
        ]


class StationViewFilter(FilterSet):
    """SatNOGS Network Station API View Filter"""

    BOOLEAN_WIDGET_CHOICES = [
        (None, "Any"),
        (True, "Yes"),
        (False, "No"),
    ]

    STATUS_WIDGET_CHOICES = [
        ("online", "Online"),
        ("testing", "Testing"),
        ("offline", "Offline"),
    ]
    status = django_filters.ChoiceFilter(
        label='Status (Deprecated)',
        method='filter_status',
        choices=STATUS_WIDGET_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    connected = django_filters.BooleanFilter(
        label='Is connected',
        method='filter_is_connected',
        widget=forms.Select(choices=BOOLEAN_WIDGET_CHOICES, attrs={'class': 'form-control'})
    )
    is_available = django_filters.BooleanFilter(
        widget=forms.Select(choices=BOOLEAN_WIDGET_CHOICES, attrs={'class': 'form-control'})
    )
    testing = django_filters.BooleanFilter(
        widget=forms.Select(choices=BOOLEAN_WIDGET_CHOICES, attrs={'class': 'form-control'})
    )

    def filter_is_connected(self, queryset, name, value):  # pylint:disable=unused-argument
        """Custom filter logic"""
        threshold = now() - timedelta(minutes=int(settings.STATION_HEARTBEAT_TIME))
        if value:
            return queryset.filter(last_seen__gte=threshold)
        return queryset.filter(Q(last_seen__lt=threshold) | Q(last_seen__isnull=True))

    def filter_status(self, queryset, name, value):  # pylint:disable=unused-argument
        """Custom filter logic"""
        threshold = now() - timedelta(minutes=int(settings.STATION_HEARTBEAT_TIME))
        if value == 'online':
            return queryset.filter(
                Q(last_seen__gte=threshold) & Q(is_available=True) & Q(testing=False)
            )
        if value == 'testing':
            return queryset.filter(
                Q(last_seen__gte=threshold) & Q(is_available=True) & Q(testing=True)
            )
        if value == 'offline':
            return queryset.filter(
                Q(last_seen__lt=threshold) | Q(last_seen__isnull=True) | Q(is_available=False)
            )
        return queryset

    class Meta:
        model = Station
        fields = ['id', 'name', 'connected', 'is_available', 'testing', 'client_version', 'status']
