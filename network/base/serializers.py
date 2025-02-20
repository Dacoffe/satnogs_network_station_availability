"""SatNOGS Network base serializers"""
from rest_framework import serializers

from network.base.models import Station


class StationSerializer(serializers.ModelSerializer):
    """Django model Serializer for Station model"""

    class Meta:
        model = Station
        fields = ('name', 'lat', 'lng', 'id', 'testing', 'status_label')
