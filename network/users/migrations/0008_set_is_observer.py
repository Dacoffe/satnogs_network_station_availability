from django.conf import settings
from django.db import migrations
from django.db.models import Exists, OuterRef


def set_is_observer(apps, schema_editor):
    User = apps.get_model('users', 'User')
    Observation = apps.get_model('base', 'Observation')

    observation_exists = Observation.objects.filter(author=OuterRef('pk')).only('id')

    users_with_observations = User.objects.annotate(has_observation=Exists(observation_exists)
                                                    ).filter(has_observation=True)

    users_with_observations.update(is_observer=True)


def reverse_set_is_observer(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(is_observer=True).update(is_observer=False)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_user_is_observer'),
    ]

    operations = [
        migrations.RunPython(set_is_observer, reverse_set_is_observer),
    ]
