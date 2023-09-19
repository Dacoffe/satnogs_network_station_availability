"""Django base views for SatNOGS Network"""
from math import ceil
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import now, timedelta
from django.views.generic import ListView

from network.base.db_api import DBConnectionError, get_transmitters_by_norad_id
from network.base.decorators import ajax_required
from network.base.models import Observation, Satellite, Station
from network.base.perms import delete_perms, schedule_perms, vet_perms
from network.base.rating_tasks import rate_observation
from network.base.stats import satellite_stats_by_transmitter_list, transmitters_with_stats
from network.base.utils import community_get_discussion_details
from network.users.models import User


def get_two_days_ago():
    """Helper function to get the datetime 48 hours before as formatted string"""
    return (now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")


class ObservationListView(ListView):  # pylint: disable=R0901
    """
    Displays a list of observations with pagination
    """
    model = Observation
    context_object_name = "observations"
    paginate_by = settings.ITEMS_PER_PAGE
    template_name = 'base/observations.html'
    str_filters = [
        'norad', 'observer', 'station', 'start', 'end', 'transmitter_mode', 'transmitter_uuid'
    ]
    flag_filters = ['bad', 'good', 'unknown', 'future', 'failed']
    filtered = None
    more_filtered = None  # Filtered by filters hidden by default

    def get_filter_params(self):
        """
        Get the parsed filter parameters from the HTTP GET parameters

        - str_filters vaues are str, default to ''
        - flag_filters values are Boolean, default to False

        Returns a dict, filter_name is the key, the parsed parameter is the value.
        """
        filter_params = {}
        for parameter_name in self.str_filters:
            filter_params[parameter_name] = self.request.GET.get(parameter_name, '')

        for parameter_name in self.flag_filters:
            param = self.request.GET.get(parameter_name, 1)
            filter_params[parameter_name] = (param != '0')

        return filter_params

    def get_queryset(self):
        """
        Optionally filter based on norad get argument
        Optionally filter based on future/good/bad/unknown/failed
        """
        filter_params = self.get_filter_params()

        results = self.request.GET.getlist('results')
        rated = self.request.GET.getlist('rated')

        observations = Observation.objects.prefetch_related(
            'satellite', 'demoddata', 'author', 'ground_station'
        )

        # Mapping between the HTTP POST parameters and the fiter keys
        parameter_filter_mapping = {
            'norad': 'satellite__norad_cat_id',
            'observer': 'author',
            'station': 'ground_station_id',
            'start': 'start__gt',
            'end': 'end__lt',
            'transmitter_mode': 'transmitter_mode__icontains',
            'transmitter_uuid': 'transmitter_uuid__icontains',
        }

        # Create observations filter based on the received HTTP POST parameters
        filter_dict = {}
        for parameter_key, filter_key in parameter_filter_mapping.items():
            if filter_params[parameter_key] == '':
                continue

            filter_dict[filter_key] = filter_params[parameter_key]

        self.filtered = bool(
            (
                not all(
                    [
                        filter_params['bad'], filter_params['good'], filter_params['unknown'],
                        filter_params['future'], filter_params['failed']
                    ]
                )
            ) or results or rated or filter_dict
        )

        # If user has not filtered the results, display the observations of the last 48 hours
        if not self.filtered:
            filter_dict["start__gt"] = get_two_days_ago()

        # If the user has used the extra filters, display hte extra filter section expaned
        self.more_filtered = (
            results or rated or filter_dict.get('author') or filter_dict.get('ground_station_id')
            or filter_dict.get('transmitter_mode__icontains')
            or filter_dict.get('transmitter_uuid__icontains')
        )

        observations = observations.filter(**filter_dict)

        if not filter_params['failed']:
            observations = observations.exclude(status__lt=-100)
        if not filter_params['bad']:
            observations = observations.exclude(status__range=(-100, -1))
        if not filter_params['unknown']:
            observations = observations.exclude(status__range=(0, 99), end__lte=now())
        if not filter_params['future']:
            observations = observations.exclude(end__gt=now())
        if not filter_params['good']:
            observations = observations.exclude(status__gte=100)

        if results:
            if 'w0' in results:
                observations = observations.filter(waterfall_old='', waterfall='')
            elif 'w1' in results:
                observations = observations.exclude(waterfall_old='', waterfall='')
            if 'a0' in results:
                observations = observations.filter(archived=False, payload_old='', payload='')
            elif 'a1' in results:
                observations = observations.exclude(archived=False, payload_old='', payload='')
            if 'd0' in results:
                observations = observations.filter(
                    demoddata__payload_demod__isnull=True,
                    demoddata__demodulated_data__isnull=True
                )
            elif 'd1' in results:
                observations = observations.exclude(
                    demoddata__payload_demod__isnull=True,
                    demoddata__demodulated_data__isnull=True
                )
            if 'i1' in results:
                observations = observations.filter(demoddata__is_image=True)

        if rated:
            if 'rwu' in rated:
                observations = observations.filter(waterfall_status__isnull=True).exclude(
                    waterfall_old='', waterfall=''
                )
            elif 'rw1' in rated:
                observations = observations.filter(waterfall_status=True)
            elif 'rw0' in rated:
                observations = observations.filter(waterfall_status=False)
        return observations

    def get_context_data(self, **kwargs):  # pylint: disable=W0221
        """
        Need to add a list of satellites to the context for the template
        """
        context = super().get_context_data(**kwargs)
        context['satellites'] = Satellite.objects.all()
        context['authors'] = User.objects.all().order_by('first_name', 'last_name', 'username')
        context['stations'] = Station.objects.all().order_by('id')
        norad_cat_id = self.request.GET.get('norad', None)
        observer = self.request.GET.get('observer', None)
        station = self.request.GET.get('station', None)
        start = get_two_days_ago() if not self.filtered else self.request.GET.get('start')
        end = self.request.GET.get('end', None)
        transmitter_uuid = self.request.GET.get('transmitter_uuid', None)
        context['display_no_filter_warning'] = not self.filtered
        context['future'] = self.request.GET.get('future', '1')
        context['bad'] = self.request.GET.get('bad', '1')
        context['good'] = self.request.GET.get('good', '1')
        context['unknown'] = self.request.GET.get('unknown', '1')
        context['failed'] = self.request.GET.get('failed', '1')
        context['results'] = self.request.GET.getlist('results')
        context['rated'] = self.request.GET.getlist('rated')
        context['transmitter_mode'] = self.request.GET.get('transmitter_mode', None)
        context['transmitter_uuids_info'] = \
            Observation.objects.all().prefetch_related(
                'satellite').order_by('transmitter_uuid').values(
            'transmitter_uuid', 'satellite__norad_cat_id', 'satellite__name').distinct()
        context['more_filtered'] = bool(self.more_filtered)
        if norad_cat_id is not None and norad_cat_id != '':
            context['norad'] = int(norad_cat_id)
        if observer is not None and observer != '':
            context['observer_id'] = int(observer)
        if station is not None and station != '':
            context['station_id'] = int(station)
        if start is not None and start != '':
            context['start'] = start
        if end is not None and end != '':
            context['end'] = end
        if 'scheduled' in self.request.session:
            context['scheduled'] = self.request.session['scheduled']
            try:
                del self.request.session['scheduled']
            except KeyError:
                pass
        if transmitter_uuid:
            context['transmitters_uuid'] = transmitter_uuid
        context['can_schedule'] = schedule_perms(self.request.user)

        url_query = urlparse(self.request.build_absolute_uri()).query
        if not url_query:
            vet_url_query = 'results=w1'
        else:
            vet_url_query = url_query.replace('results=w0', 'results=w1')
            if vet_url_query == url_query:  # no 'results' parameter was given
                vet_url_query += '&results=w1'
        context['vet_url_query'] = vet_url_query
        return context


def get_observation_demoddata_details(observation, demoddata, demoddata_count):
    """Returns details about the Demoddata of the observation"""
    demoddata_details = []
    show_hex_to_ascii_button = False
    if demoddata_count:
        if observation.transmitter_mode == 'CW':
            content_type = 'text'
        else:
            content_type = 'binary'

        for datum in demoddata:
            if datum.is_image:
                if datum.payload_demod:
                    demoddata_details.append(
                        {
                            'url': datum.payload_demod.url,
                            'name': datum.payload_demod.name,
                            'type': 'image'
                        }
                    )
                else:
                    demoddata_details.append(
                        {
                            'url': datum.demodulated_data.url,
                            'name': datum.demodulated_data.name,
                            'type': 'image'
                        }
                    )
            else:
                show_hex_to_ascii_button = True
                if datum.payload_demod:
                    demoddata_details.append(
                        {
                            'url': datum.payload_demod.url,
                            'name': datum.payload_demod.name,
                            'type': content_type
                        }
                    )
                else:
                    demoddata_details.append(
                        {
                            'url': datum.demodulated_data.url,
                            'name': datum.demodulated_data.name,
                            'type': content_type
                        }
                    )
        demoddata_details = sorted(demoddata_details, key=lambda d: d['name'])
    return demoddata_details, show_hex_to_ascii_button


class VetObservationAbstractView(LoginRequiredMixin, ObservationListView):  # pylint: disable=R0901
    """View to vet multiple observations."""
    template_name = ''
    object_list = []

    def get_queryset(self):
        """ Limits the queryset to those observations that the user can vet.
            works, similar to 'vet_perms' function.
        """
        queryset = super().get_queryset().annotate(demoddata_count=Count('demoddata'))
        if not (self.request.user.is_superuser
                or self.request.user.groups.filter(name='Moderators').exists()
                or self.request.user.has_perm('base.can_vet')
                or self.request.user.ground_stations.filter(status=2).exists()):
            queryset = queryset.filter(
                Q(author=self.request.user)
                | Q(ground_station__isnull=False, ground_station__owner=self.request.user)
            )
        return queryset.order_by('-id')

    def get(self, request, *args, **kwargs):
        pass


class VetObservationsChunkListView(VetObservationAbstractView):  # pylint: disable=R0901
    """View for getting the observations to vet as HTML snippets"""
    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        paginator = Paginator(queryset, settings.VET_ITEMS_PER_CHUNK)
        page_num = request.GET.get('page')
        page_obj = paginator.get_page(page_num)
        obs_html = []
        for obs in page_obj.object_list:
            demoddata_details = get_observation_demoddata_details(
                obs, obs.demoddata.all(), obs.demoddata_count
            )

            context = {
                "observation": obs,
                "from_vetting": True,
                "can_vet": True,
                "demoddata_count": obs.demoddata_count,
                "demoddata_details": demoddata_details[0],
                "show_hex_to_ascii_button": demoddata_details[1],
            }
            context.update(csrf(request))

            rendered = render_to_string("includes/observation_detail.html", context)
            obs_html.append(rendered)

        return JsonResponse(obs_html, safe=False)


class VetObservationsView(VetObservationAbstractView):  # pylint: disable=R0901
    """View for vetting multiple observations"""
    template_name = 'base/vet_observation_container.html'

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        queryset_count = queryset.count()
        context = {}
        parsed_url = urlparse(request.build_absolute_uri())
        context["query_url"] = reverse('base:vet_observations_chunks') + '?' + parsed_url.query
        context["observation_search_url"
                ] = reverse('base:observations_list') + '?' + parsed_url.query
        context["page_size"] = settings.VET_ITEMS_PER_CHUNK
        context["total_pages_num"] = ceil(queryset_count / settings.VET_ITEMS_PER_CHUNK)
        context["total_items"] = queryset_count
        context["chunks_buffer_headstart"] = settings.CHUNKS_BUFFER_HEADSTART
        context["fwd_buffer_chunks"] = settings.FWD_BUFFER_CHUNKS
        context["bwd_buffer_chunks"] = settings.BWD_BUFFER_CHUNKS
        return self.render_to_response(context)


def observation_view(request, observation_id):
    """View for single observation page."""
    observation = get_object_or_404(Observation, id=observation_id)

    can_vet = vet_perms(request.user, observation)

    can_delete = delete_perms(request.user, observation)

    if observation.has_audio and not observation.audio_url:
        messages.error(
            request, 'Audio file is not currently available,'
            ' if the problem persists please contact an administrator.'
        )

    has_comments = False
    discuss_url = ''
    discuss_slug = ''
    if settings.ENVIRONMENT == 'production':
        discussion_details = community_get_discussion_details(
            observation.id, observation.satellite.name, observation.satellite.norad_cat_id,
            'https:%2F%2F{}{}'.format(request.get_host(), request.path)
        )
        has_comments = discussion_details['has_comments']
        discuss_url = discussion_details['url']
        discuss_slug = discussion_details['slug']

    demoddata_count = observation.demoddata.count()
    demoddata = observation.demoddata.all()
    demoddata_details, show_hex_to_ascii_button = get_observation_demoddata_details(
        observation, demoddata, demoddata_count
    )

    return render(
        request, 'base/observation_view.html', {
            'observation': observation,
            'demoddata_count': demoddata_count,
            'demoddata_details': demoddata_details,
            'show_hex_to_ascii_button': show_hex_to_ascii_button,
            'can_vet': can_vet,
            'can_delete': can_delete,
            'has_comments': has_comments,
            'discuss_url': discuss_url,
            'discuss_slug': discuss_slug
        }
    )


@login_required
def observation_delete(request, observation_id):
    """View for deleting observation."""
    observation = get_object_or_404(Observation, id=observation_id)
    can_delete = delete_perms(request.user, observation)
    if can_delete:
        observation.delete()
        messages.success(request, 'Observation deleted successfully.')
    else:
        messages.error(request, 'Permission denied.')
    return redirect(reverse('base:observations_list'))


@login_required
@ajax_required
def waterfall_vet(request, observation_id):
    """Handles request for vetting a waterfall"""
    try:
        observation = Observation.objects.get(id=observation_id)
    except Observation.DoesNotExist:
        data = {'error': 'Observation does not exist.'}
        return JsonResponse(data, safe=False)

    status = request.POST.get('status', None)
    can_vet = vet_perms(request.user, observation)

    if not can_vet:
        data = {'error': 'Permission denied.'}
        return JsonResponse(data, safe=False)
    if not observation.has_waterfall:
        data = {'error': 'Observation without waterfall.'}
        return JsonResponse(data, safe=False)

    if status not in ['with-signal', 'without-signal', 'unknown']:
        data = {
            'error': 'Invalid status, select one of \'with-signal\', \'without-signal\' and '
            '\'unknown\'.'
        }
        return JsonResponse(data, safe=False)

    if status == 'with-signal':
        observation.waterfall_status = True
    elif status == 'without-signal':
        observation.waterfall_status = False
    elif status == 'unknown':
        observation.waterfall_status = None

    observation.waterfall_status_user = request.user
    observation.waterfall_status_datetime = now()
    observation.save(
        update_fields=['waterfall_status', 'waterfall_status_user', 'waterfall_status_datetime']
    )
    (observation_status, observation_status_badge, observation_status_display
     ) = rate_observation(observation.id, 'set_waterfall_status', observation.waterfall_status)
    data = {
        'waterfall_status_user': observation.waterfall_status_user.displayname,
        'waterfall_status_datetime': observation.waterfall_status_datetime.
        strftime('%Y-%m-%d %H:%M:%S'),
        'waterfall_status': observation.waterfall_status,
        'waterfall_status_badge': observation.waterfall_status_badge,
        'waterfall_status_display': observation.waterfall_status_display,
        'status': observation_status,
        'status_badge': observation_status_badge,
        'status_display': observation_status_display,
    }
    return JsonResponse(data, safe=False)


def satellite_view(request, norad_id):
    """Returns a satellite JSON object with information and statistics"""
    try:
        sat = Satellite.objects.get(norad_cat_id=norad_id)
    except Satellite.DoesNotExist:
        data = {'error': 'Unable to find that satellite.'}
        return JsonResponse(data, safe=False)

    try:
        transmitters = get_transmitters_by_norad_id(norad_id=norad_id)
    except DBConnectionError as error:
        data = [{'error': str(error)}]
        return JsonResponse(data, safe=False)
    satellite_stats = satellite_stats_by_transmitter_list(transmitters)
    data = {
        'id': norad_id,
        'name': sat.name,
        'names': sat.names,
        'image': sat.image,
        'success_rate': satellite_stats['success_rate'],
        'good_count': satellite_stats['good_count'],
        'bad_count': satellite_stats['bad_count'],
        'unknown_count': satellite_stats['unknown_count'],
        'future_count': satellite_stats['future_count'],
        'total_count': satellite_stats['total_count'],
        'transmitters': transmitters_with_stats(transmitters)
    }

    return JsonResponse(data, safe=False)
