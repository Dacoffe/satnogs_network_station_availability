"""Django database base model for SatNOGS Network"""
from django.db.models.signals import post_save, pre_delete
from django.utils.timezone import now

from network.base.models import Station


def _station_post_save(sender, instance, created, **kwargs):  # pylint: disable=W0613
    """
    Post save Station operations
    * Store current status
    """
    post_save.disconnect(_station_post_save, sender=Station)
    instance.update_status(created=created)
    post_save.connect(_station_post_save, sender=Station)


def _station_pre_delete(sender, instance, **kwargs):  # pylint: disable=W0613
    """
    Pre delete Station operations
    * Delete future observation of deleted station
    """
    instance.observations.filter(start__gte=now()).delete()


post_save.connect(_station_post_save, sender=Station)

pre_delete.connect(_station_pre_delete, sender=Station)
