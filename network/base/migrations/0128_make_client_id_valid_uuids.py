from uuid import uuid4

from django.db import migrations, transaction


def convert_client_ids_to_valid_uuid(apps, schema_editor):
    Station = apps.get_model('base', 'Station')

    with transaction.atomic():
        Station.objects.filter(client_id='').update(client_id=None)
        stations = list(Station.objects.filter(client_id__isnull=False))
        for s in stations:
            s.client_id = str(uuid4()).replace('-', '')
        Station.objects.bulk_update(stations, ['client_id'])


def revert_client_ids_to_string(apps, schema_editor):
    Station = apps.get_model('base', 'Station')
    Station.objects.filter(client_id__isnull=True).update(client_id='')


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0127_alter_station_client_id'),
    ]

    operations = [
        migrations.RunPython(convert_client_ids_to_valid_uuid, revert_client_ids_to_string)
    ]
