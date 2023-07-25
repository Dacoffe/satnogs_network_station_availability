"""SatNOGS Network API django rest framework Views"""
from random import choices
from string import ascii_letters, digits

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count
from django.db.models.query import QuerySet
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.serializers import ValidationError

from network.api import authentication, filters, pagination, serializers
from network.api.perms import StationOwnerPermission
from network.base.models import Observation, Station
from network.base.rating_tasks import rate_observation
from network.base.tasks import delay_task_with_lock, process_audio, sync_frame_to_db
from network.base.validators import NegativeElevationError, NoTleSetError, \
    ObservationOverlapError, SchedulingLimitError, SinglePassError


class ObservationView(  # pylint: disable=R0901
        mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
        mixins.CreateModelMixin, viewsets.GenericViewSet):
    """SatNOGS Network Observation API view class"""
    filterset_class = filters.ObservationViewFilter
    pagination_class = pagination.LinkedHeaderPageNumberPagination

    def get_permissions(self):
        if self.action in ('update', 'create'):
            self.permission_classes = [StationOwnerPermission]
        return super().get_permissions()

    def get_queryset(self):
        if self.action == 'update':
            queryset = Observation.objects.select_for_update()
        else:
            queryset = Observation.objects.prefetch_related('demoddata').select_related(
                'satellite', 'ground_station', "waterfall_status_user", "author"
            )
        if isinstance(queryset, QuerySet):
            # Ensure queryset is re-evaluated on each request.
            queryset = queryset.all()
        return queryset

    def get_serializer_class(self):
        """Returns the right serializer depending on http method that is used"""
        if self.action == 'create':
            return serializers.NewObservationSerializer
        if self.action == 'update':
            return serializers.UpdateObservationSerializer
        return serializers.ObservationSerializer

    def create(self, request, *args, **kwargs):
        """Creates observations from a list of observation data"""
        serializer = self.get_serializer(data=request.data, many=True, allow_empty=False)
        try:
            if serializer.is_valid():
                observations = serializer.save()
                serialized_obs = serializers.ObservationSerializer(observations, many=True)
                data = serialized_obs.data
                response = Response(data, status=status.HTTP_200_OK)
            else:
                data = serializer.errors
                response = Response(data, status=status.HTTP_400_BAD_REQUEST)
        except (NegativeElevationError, SinglePassError, ValidationError, ValueError) as error:
            response = Response(str(error), status=status.HTTP_400_BAD_REQUEST)
        except NoTleSetError as error:
            response = Response(str(error), status=status.HTTP_501_NOT_IMPLEMENTED)
        except (ObservationOverlapError, SchedulingLimitError) as error:
            response = Response(str(error), status=status.HTTP_409_CONFLICT)
        return response

    def update(self, request, *args, **kwargs):
        """Updates observation with audio, waterfall or demoded data"""
        observation_has_data = False
        demoddata_id = None
        with transaction.atomic():
            instance = self.get_object()
            if request.data.get('client_version'):
                instance.ground_station.client_version = request.data.get('client_version')
                instance.ground_station.save()
            if request.data.get('demoddata'):
                try:
                    name = 'data_obs/{0}/{1}/{2}/{3}/{4}/{5}'.format(
                        instance.start.year, instance.start.month, instance.start.day,
                        instance.start.hour, instance.id, request.data.get('demoddata')
                    )
                    instance.demoddata.get(demodulated_data=name)
                    return Response(
                        data='This data file has already been uploaded',
                        status=status.HTTP_403_FORBIDDEN
                    )
                except ObjectDoesNotExist:
                    # Check if observation has data before saving the current ones
                    observation_has_data = instance.demoddata.exists()
                    demoddata_serializer = serializers.CreateDemodDataSerializer(
                        data={
                            'observation': instance.pk,
                            'demodulated_data': request.data.get('demoddata')
                        }
                    )
                    demoddata_serializer.is_valid(raise_exception=True)
                    demoddata = demoddata_serializer.save()
                    demoddata_id = demoddata.id
            if request.data.get('waterfall'):
                if instance.has_waterfall:
                    return Response(
                        data='Watefall has already been uploaded',
                        status=status.HTTP_403_FORBIDDEN
                    )
            if request.data.get('payload'):
                if instance.has_audio:
                    return Response(
                        data='Audio has already been uploaded', status=status.HTTP_403_FORBIDDEN
                    )

            # False-positive no-member (E1101) pylint error:
            # Parent class rest_framework.mixins.UpdateModelMixin provides the 'update' method
            super().update(request, *args, **kwargs)  # pylint: disable=E1101

        if request.data.get('waterfall'):
            rate_observation.delay(instance.id, 'waterfall_upload')
        # Rate observation only on first demoddata uploading
        if request.data.get('demoddata') and demoddata_id:
            sync_frame_to_db.delay(frame_id=demoddata_id)
            if not observation_has_data:
                rate_observation.delay(instance.id, 'data_upload')
        if request.data.get('payload'):
            delay_task_with_lock(
                process_audio, instance.id, settings.PROCESS_AUDIO_LOCK_EXPIRATION, instance.id
            )
        return Response(status=status.HTTP_200_OK)


class StationView(  # pylint: disable=R0901
        mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """SatNOGS Network Station API view class"""
    queryset = Station.objects.annotate(
        total_obs=Count('observations'),
    ).order_by('id').prefetch_related(
        'antennas', 'antennas__antenna_type', 'antennas__frequency_ranges'
    )
    serializer_class = serializers.StationSerializer
    filterset_class = filters.StationViewFilter
    pagination_class = pagination.LinkedHeaderPageNumberPagination


class StationConfigurationView(viewsets.ReadOnlyModelViewSet):  # pylint: disable=R0901
    """SatNOGS Network Station Configuration API view class"""
    queryset = Station.objects.all()
    serializer_class = serializers.StationConfigurationSerializer
    authentication_classes = [authentication.ClientIDAuthentication]
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        station = get_object_or_404(Station, client_id=request.auth)
        return HttpResponseRedirect(redirect_to='/api/configuration/' + str(station.id) + '/')


@api_view(['POST'])
@permission_classes((AllowAny, ))
def station_register_view(request):
    """ API endpoint for receiving client_id and return url for registering new station or connect
        client_id to existing one
    """
    client_id = request.POST.get('client_id', None)
    if client_id:
        if Station.objects.filter(client_id=client_id).exists():
            error = 'Invalid Client ID, please restart the "Station Registration" process.'
            return Response(error, status=status.HTTP_400_BAD_REQUEST)
        url_hash = ''.join(choices(ascii_letters + digits, k=60))
        cache.set(url_hash, client_id, 60 * 10)
        path = reverse('base:station_register', kwargs={'step': 1}) + '?hash=' + url_hash
        url = request.build_absolute_uri(path)
        return Response(data={'url': url}, status=status.HTTP_200_OK)
    return HttpResponseRedirect(redirect_to='/api/')


class TransmitterView(  # pylint: disable=R0901
        mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """SatNOGS Network Transmitter API view class"""
    queryset = Observation.objects.order_by().values('transmitter_uuid').distinct()
    serializer_class = serializers.TransmitterSerializer
    lookup_field = 'transmitter_uuid'
    filterset_class = filters.TransmitterViewFilter
    pagination_class = pagination.LinkedHeaderPageNumberPagination


class JobView(viewsets.ReadOnlyModelViewSet):  # pylint: disable=R0901
    """SatNOGS Network Job API view class"""
    queryset = Observation.objects.all()
    filterset_class = filters.ObservationViewFilter
    serializer_class = serializers.JobSerializer
    filterset_fields = ('ground_station')

    def list(self, request, *args, **kwargs):
        lat = self.request.query_params.get('lat', None)
        lon = self.request.query_params.get('lon', None)
        alt = self.request.query_params.get('alt', None)
        ground_station_id = self.request.query_params.get('ground_station', None)
        if ground_station_id and self.request.user.is_authenticated:
            ground_station = get_object_or_404(Station, id=ground_station_id)
            if ground_station.owner == self.request.user:
                if not (lat is None or lon is None or alt is None):
                    data = {"lat": lat, "lng": lon, "altitude": alt, "last_seen": now()}
                else:
                    data = {"last_seen": now()}

                serializer = serializers.StationSerializer(ground_station, data=data, partial=True)
                if serializer.is_valid() is False:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

                serializer.save()

        job_serializer = serializers.JobSerializer(
            self.filter_queryset(self.get_queryset()), many=True
        )
        return Response(job_serializer.data, status=status.HTTP_200_OK)

    def get_queryset(self):
        """Returns queryset for Job API view"""
        queryset = self.queryset.filter(start__gte=now())

        return queryset
