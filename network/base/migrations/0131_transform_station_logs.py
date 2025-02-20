from itertools import groupby
from operator import attrgetter

from django.db import migrations, transaction


def transform_station_status(apps, schema_editor):
    Station = apps.get_model('base', 'Station')
    StationStatusLog = apps.get_model('base', 'StationStatusLog')
    offline_station_ids = list(
        Station.objects.filter(status=0, testing=False).values_list('id', flat=True)
    )
    with transaction.atomic():
        Station.objects.filter(id__in=offline_station_ids).update(testing=True)
        for station_id in offline_station_ids:
            StationStatusLog.objects.create(
                station_id=station_id, testing=True, is_available=True, is_connected=False
            )


def transform_station_logs(apps, schema_editor):
    Station = apps.get_model('base', 'Station')
    StationStatusLog = apps.get_model('base', 'StationStatusLog')
    station_ids = list(Station.objects.values_list('id', flat=True))
    for station_id in station_ids:
        station_logs = list(
            StationStatusLog.objects.filter(station_id=station_id).order_by('changed')
        )
        if not station_logs:
            continue
        was_testing = False
        for log in station_logs:
            if log.status == 1:
                was_testing = True
                log.testing = True
                log.is_available = False
                log.is_connected = True
            elif log.status == 2:
                was_testing = False
                log.is_connected = True
            else:
                log.testing = was_testing
                log.is_available = not was_testing
        StationStatusLog.objects.bulk_update(
            station_logs, ['testing', 'is_connected', 'is_available']
        )


class Migration(migrations.Migration):

    dependencies = [('base', '0130_alter_station_options_and_more')]
    operations = [
        migrations.RunPython(transform_station_logs),
        migrations.RunPython(transform_station_status),
        migrations.RemoveIndex(
            model_name='station',
            name='base_statio_status_797b1c_idx',
        ),
        migrations.RemoveField(
            model_name='station',
            name='status',
        ),
        migrations.RemoveField(
            model_name='stationstatuslog',
            name='status',
        ),
    ]
