"""SatNOGS Network API django rest framework Views"""
from random import choices
from string import ascii_letters, digits

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.serializers import ValidationError

from network.api import authentication, filters, pagination, serializers
from network.api.perms import StationOwnerPermission
from network.api.throttling import GetObservationAnononymousRateThrottle, \
    GetStationAnononymousRateThrottle
from network.base.models import ActiveStationConfiguration, Observation, Station
from network.base.rating_tasks import rate_observation
from network.base.stats import get_transmitter_with_stats_by_uuid
from network.base.tasks import delay_task_with_lock, \
    get_and_refresh_transmitters_with_stats_cache, process_audio, sync_frame_to_db
from network.base.utils import get_api_url
from network.base.validators import NegativeElevationError, NoTleSetError, \
    ObservationOverlapError, SchedulingLimitError, SinglePassError


class ObservationView(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                      mixins.CreateModelMixin, viewsets.GenericViewSet):
    """SatNOGS Network Observation API view class"""
    filterset_class = filters.ObservationViewFilter
    pagination_class = pagination.ObservationCursorPagination

    def get_permissions(self):
        if self.action in ('update', 'create'):
            self.permission_classes = [StationOwnerPermission]
        return super().get_permissions()

    def get_throttles(self):
        self.throttle_classes = []
        if self.action == 'list':
            self.throttle_classes.append(GetObservationAnononymousRateThrottle)
        return super().get_throttles()

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

    def list(self, request, *args, **kwargs):
        if request.GET.get('page'):
            data = [
                {
                    'error': (
                        'Parameter \'page\' is now deprecated, please use \'Link\' header for'
                        ' getting URLs for next/previous pages.'
                    )
                }
            ]
            response = Response(data, status=status.HTTP_400_BAD_REQUEST)
            response.exception = True
            return response

        return super().list(request, *args, **kwargs)

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


class StationView(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """SatNOGS Network Station API view class"""
    serializer_class = serializers.StationSerializer
    filterset_class = filters.StationViewFilter
    pagination_class = pagination.LinkedHeaderPageNumberPagination

    def get_throttles(self):
        self.throttle_classes = []
        if self.action == 'list':
            self.throttle_classes.append(GetStationAnononymousRateThrottle)
        return super().get_throttles()

    def get_queryset(self):
        """Queryset for station model in the API"""
        future_obs_subquery = Observation.objects.filter(
            ground_station_id=OuterRef('id'), end__gt=now()
        ).values('ground_station_id').annotate(c=Count('id')).values('c')

        stations = Station.objects.annotate(
            total_obs=Count('observations'),
            future_obs=Coalesce(Subquery(future_obs_subquery, output_field=IntegerField()), 0)
        ).select_related('owner').prefetch_related(
            'antennas', 'antennas__antenna_type', 'antennas__frequency_ranges'
        ).order_by('-status', 'id')

        return stations


class StationConfigurationView(viewsets.ReadOnlyModelViewSet):
    """SatNOGS Network Station Configuration API view class"""
    queryset = ActiveStationConfiguration.objects.all()
    serializer_class = serializers.StationConfigurationSerializer
    authentication_classes = [authentication.ClientIDAuthentication]
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        configuration = get_object_or_404(
            ActiveStationConfiguration, station__client_id=request.auth
        )
        configuration.configuration['Network Configuration'] = {
            "station_id": configuration.station.pk,
            "api_url": get_api_url(),
            "api_token": configuration.station.owner.auth_token.key
        }
        return Response(configuration.configuration)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs['pk'] if kwargs['pk'].isdigit() else None  # pylint: disable=C0103
        configuration = get_object_or_404(
            ActiveStationConfiguration, pk=pk, station__client_id=request.auth
        )
        configuration.configuration['Network Configuration'] = {
            "station_id": configuration.station.pk,
            "api_url": get_api_url(),
            "api_token": configuration.station.owner.auth_token.key
        }
        return Response(configuration.configuration)


@extend_schema(
    operation_id="station_register",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string"
                },
            },
            "required": ["client_id"]
        }
    },
    responses={
        status.HTTP_200_OK: inline_serializer(
            name='RegistrationSuccessResponse',
            fields={'url': str},
        ),
        status.HTTP_400_BAD_REQUEST: inline_serializer(
            name='ErrorResponse',
            fields={'detail': str},
        ),
        status.HTTP_302_FOUND: None
    },
    summary="Register a new station or connect to an existing one",
    description=(
        "API endpoint for receiving client_id and return url for registering new"
        " station or connecting client_id to an existing one."
    ),
    tags=["Station Registration"],
)
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


@extend_schema(
    methods=['GET'],
    operation_id="transmitters_detail",
    description="Gets details of a single transmitter along with its statistics",
    parameters=[
        OpenApiParameter(
            name="transmitter_uuid",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.PATH,
            required=True
        ),
    ],
    responses=serializers.TransmitterSerializer,
)
@api_view(['GET'])
@permission_classes((AllowAny, ))
def transmitter_detail_view(request, transmitter_uuid):
    """API detail view for transmitter"""
    transmitter = get_transmitter_with_stats_by_uuid(transmitter_uuid)
    if not transmitter:
        raise Http404
    serializer = serializers.TransmitterSerializer(transmitter)
    return Response(serializer.data)


@extend_schema(
    methods=['GET'],
    operation_id="transmitters_list",
    description="Gets details of a transmitter along with its statistics",
    parameters=[
        OpenApiParameter(
            name="uuid", type=OpenApiTypes.UUID, location=OpenApiParameter.QUERY, required=False
        ),
    ],
    responses=serializers.TransmitterSerializer
)
@api_view(['GET'])
@permission_classes((AllowAny, ))
def transmitters_view(request):
    """Transmitter list API view"""
    query_params = request.GET
    if query_params.get('uuid'):
        transmitter = get_transmitter_with_stats_by_uuid(query_params.get('uuid'))
        queryset = [transmitter] if transmitter else []
    else:
        cached_transmitters_with_stats = cache.get('transmitters-with-stats')
        queryset = cached_transmitters_with_stats.values(
        ) if cached_transmitters_with_stats else get_and_refresh_transmitters_with_stats_cache(
            in_list_form=True
        )
    serializer = serializers.TransmitterSerializer(queryset, many=True)
    return Response(serializer.data)


class JobView(viewsets.ReadOnlyModelViewSet):
    """SatNOGS Network Job API view class"""
    queryset = Observation.objects.all()
    filterset_class = filters.ObservationViewFilter
    serializer_class = serializers.JobSerializer
    filterset_fields = 'ground_station'

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
