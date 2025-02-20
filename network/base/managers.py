"""Django base manager for SatNOGS Network"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.timezone import now


class ObservationManager(models.QuerySet):
    """Observation Manager with extra functionality"""

    def is_future(self):
        """Return future observations"""
        return self.filter(end__gte=now())


class StationManagerQueryset(models.QuerySet):
    """Station queryset to be used as Manager"""

    def connected(self):
        """Returns connected stations"""
        threshold = now() - timedelta(minutes=int(settings.STATION_HEARTBEAT_TIME))
        return self.filter(last_seen__gt=threshold)

    def connected_and_located(self):
        """Returns connected stations that have a defined location and altitude"""
        threshold = now() - timedelta(minutes=int(settings.STATION_HEARTBEAT_TIME))
        return self.filter(
            last_seen__gt=threshold, alt__isnull=False, lat__isnull=False, lng__isnull=False
        )

    def disconnected(self):
        """Returns connected stations"""
        threshold = now() - timedelta(minutes=int(settings.STATION_HEARTBEAT_TIME))
        return self.filter(last_seen__lte=threshold)
