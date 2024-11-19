"""Django database base model for SatNOGS Network"""
from django.db.models.signals import post_delete, post_save, pre_delete
from django.utils.timezone import now

from network.base.models import Observation, Station


def _observation_post_delete(sender, instance, **kwargs):  # pylint: disable=W0613
    """Sets is_observer on user"""

    observer = instance.author
    if not observer.observations.count():
        observer.is_observer = False
        observer.save(update_fields=['is_observer'])


def _station_post_save(sender, instance, created, **kwargs):  # pylint: disable=W0613
    """
    Post save Station operations
    * Store current status
    """
    post_save.disconnect(_station_post_save, sender=Station)
    instance.update_status(created=created)
    post_save.connect(_station_post_save, sender=Station, weak=False)


def _station_pre_delete(sender, instance, **kwargs):  # pylint: disable=W0613
    """
    Pre delete Station operations
    * Delete future observation of deleted station
    """
    instance.observations.filter(start__gte=now()).delete()


post_save.connect(_station_post_save, sender=Station, weak=False)

pre_delete.connect(_station_pre_delete, sender=Station, weak=False)

post_delete.connect(_observation_post_delete, sender=Observation, weak=False)
