"""SatNOGS Network django rest framework API url routings"""
from django.urls import path
from rest_framework import routers

from network.api import views

DEFAULT_ROUTER = routers.DefaultRouter()

DEFAULT_ROUTER.register(r'jobs', views.JobView, basename='jobs')
DEFAULT_ROUTER.register(r'observations', views.ObservationView, basename='observations')
DEFAULT_ROUTER.register(r'stations', views.StationView, basename='stations')

SIMPLE_ROUTER = routers.SimpleRouter()

SIMPLE_ROUTER.register(r'configuration', views.StationConfigurationView, basename='configuration')

API_URLPATTERNS = DEFAULT_ROUTER.urls + SIMPLE_ROUTER.urls + [
    path('transmitters/', views.transmitters_view),
    path('transmitters/<str:transmitter_uuid>', views.transmitter_detail_view),
    path('station/register', views.station_register_view)
]
