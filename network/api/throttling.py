"""SatNOGS DB API throttling classes, django rest framework"""
from rest_framework import throttling


class GetObservationAnononymousRateThrottle(throttling.AnonRateThrottle):
    """Anonymous GET Throttling for Observation API endpoint"""
    scope = 'get_observation_anon'

    def allow_request(self, request, view):
        if request.method in ('POST', 'PUT'):
            return True
        return super().allow_request(request, view)


class GetStationAnononymousRateThrottle(throttling.AnonRateThrottle):
    """Anonymous GET Throttling for Observation API endpoint"""
    scope = 'get_station_anon'
