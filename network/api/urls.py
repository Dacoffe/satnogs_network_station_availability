"""SatNOGS Network django rest framework API url routings"""
from django.urls import path
from rest_framework import routers

from network.api import views

ROUTER = routers.DefaultRouter()

ROUTER.register(r'jobs', views.JobView, basename='jobs')
ROUTER.register(r'observations', views.ObservationView, basename='observations')
ROUTER.register(r'stations', views.StationView, basename='stations')
ROUTER.register(r'configuration', views.StationConfigurationView, basename='configuration')

API_URLPATTERNS = ROUTER.urls + [
    path('transmitters/', views.transmitters_view),
    path('transmitters/<str:transmitter_uuid>', views.transmitter_detail_view),
    path('station/register', views.station_register_view)
]
