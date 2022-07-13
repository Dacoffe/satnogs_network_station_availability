"""Django base views for SatNOGS Network"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import DatabaseError, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now

from network.base.decorators import ajax_required
from network.base.forms import AntennaInlineFormSet, FrequencyRangeInlineFormSet, StationForm, \
    StationRegistrationForm
from network.base.models import AntennaType, Station, StationStatusLog
from network.base.perms import modify_delete_station_perms, schedule_station_perms
from network.base.serializers import StationSerializer
from network.base.utils import populate_formset_error_messages


@ajax_required
def station_all_view(request):
    """Return JSON with all stations"""
    stations = Station.objects.all()
    data = StationSerializer(stations, many=True).data
    return JsonResponse(data, safe=False)


def stations_list(request):
    """View to render Stations page."""
    stations = Station.objects.annotate(
        total_obs=Count('observations'),
        future_obs=Count('pk', filter=Q(observations__end__gt=now())),
    ).prefetch_related(
        'owner', 'antennas', 'antennas__antenna_type', 'antennas__frequency_ranges'
    ).order_by('-status', 'id')
    stations_by_status = {'online': 0, 'testing': 0, 'offline': 0, 'future': 0}
    for station in stations:
        if station.last_seen is None:
            stations_by_status['future'] += 1
        elif station.status == 2:
            stations_by_status['online'] += 1
        elif station.status == 1:
            stations_by_status['testing'] += 1
        else:
            stations_by_status['offline'] += 1

    return render(
        request, 'base/stations.html', {
            'stations': stations,
            'online': stations_by_status['online'],
            'testing': stations_by_status['testing'],
            'offline': stations_by_status['offline'],
            'future': stations_by_status['future'],
            'mapbox_id': settings.MAPBOX_MAP_ID,
            'mapbox_token': settings.MAPBOX_TOKEN
        }
    )


def station_view(request, station_id):
    """View for single station page."""
    station = get_object_or_404(
        Station.objects.annotate(
            total_obs=Count('observations'),
            future_obs=Count('pk', filter=Q(observations__end__gt=now())),
        ).prefetch_related(
            'owner', 'antennas', 'antennas__antenna_type', 'antennas__frequency_ranges'
        ),
        id=station_id
    )

    can_schedule = schedule_station_perms(request.user, station)
    can_modify_delete_station = modify_delete_station_perms(request.user, station)

    # Calculate uptime
    uptime = '-'
    try:
        latest = StationStatusLog.objects.filter(station=station)[0]
    except IndexError:
        latest = None
    if latest:
        if latest.status:
            try:
                offline = StationStatusLog.objects.filter(station=station, status=0)[0]
                uptime = latest.changed - offline.changed
            except IndexError:
                uptime = now() - latest.changed
            uptime = str(uptime).split('.')[0]

    if request.user.is_authenticated:
        if request.user == station.owner:
            wiki_help = (
                '<a href="{0}" target="_blank" class="wiki-help"><span class="glyphicon '
                'glyphicon-question-sign" aria-hidden="true"></span>'
                '</a>'.format(settings.WIKI_STATION_URL)
            )
            if station.is_offline:
                messages.error(
                    request, (
                        'Your Station is offline. You should make '
                        'sure it can successfully connect to the Network API. '
                        '{0}'.format(wiki_help)
                    )
                )
            if station.is_testing:
                messages.warning(
                    request, (
                        'Your Station is in Testing mode. Once you are sure '
                        'it returns good observations you can put it online. '
                        '{0}'.format(wiki_help)
                    )
                )

    return render(
        request, 'base/station_view.html', {
            'station': station,
            'mapbox_id': settings.MAPBOX_MAP_ID,
            'mapbox_token': settings.MAPBOX_TOKEN,
            'can_schedule': can_schedule,
            'can_modify_delete_station': can_modify_delete_station,
            'uptime': uptime
        }
    )


def station_log_view(request, station_id):
    """View for single station status log."""
    station = get_object_or_404(Station, id=station_id)
    station_log = StationStatusLog.objects.filter(station=station)

    return render(
        request, 'base/station_log.html', {
            'station': station,
            'station_log': station_log
        }
    )


@login_required
def station_delete(request, station_id):
    """View for deleting a station."""
    username = request.user
    station = get_object_or_404(Station, id=station_id, owner=request.user)
    station.delete()
    messages.success(request, 'Ground Station deleted successfully.')
    return redirect(reverse('users:view_user', kwargs={'username': username}))


@login_required
def station_delete_future_observations(request, station_id):
    """View for deleting all future observations of a given station."""
    return redirect(reverse('base:station_view', kwargs={'station_id': station_id}))
    # station = get_object_or_404(Station, id=station_id)

    # if not modify_delete_station_perms(request.user, station):
    #     messages.error(
    #         request,
    #         'You are not allowed to bulk-delete future observations on ground station {}!'.
    #         format(station_id)
    #     )
    #     return redirect(reverse('base:station_view', kwargs={'station_id': station_id}))

    # count, _ = station.observations.filter(start__gte=now()).delete()
    # if count:
    #     messages.success(
    #         request,
    #         'Deleted {} future observations on ground station {}.'.format(count, station_id)
    #     )
    # else:
    #     messages.success(
    #         request, 'No future observations on ground station {}.'.format(station_id)
    #     )
    # return redirect(reverse('base:station_view', kwargs={'station_id': station_id}))


@login_required
def station_register(request, step=None, station_id=None):
    """ Station register view """
    client_hash = request.GET.get('hash', None)
    if client_hash:
        client_id = cache.get(client_hash)
        if client_id is None:
            messages.error(
                request,
                'Invalid or expired hash, please restart the "Station Registration" process.'
            )
            return redirect(reverse('base:home'))
    else:
        messages.error(request, 'Missing hash parameter.')
        return redirect(reverse('base:home'))
    if step == '1':
        stations = Station.objects.filter(owner=request.user)
        return render(
            request, 'base/station_register_step1.html', {
                'client_hash': client_hash,
                'stations': stations
            }
        )
    if step == '2':
        station = None
        if station_id:
            station = get_object_or_404(Station, id=station_id, owner=request.user)

        if request.method == 'POST':
            if station:
                station_form = StationRegistrationForm(request.POST, instance=station)
            else:
                station_form = StationRegistrationForm(request.POST)
            if station_form.is_valid():
                station = station_form.save(commit=False)
                station.owner = request.user
                station.save()
                cache.delete(client_hash)
                messages.success(
                    request, (
                        'Ground Station {0} is registered successfully.'
                        ' Continue now with its configuration.'
                    ).format(station.id)
                )
                return redirect(reverse('base:station_edit', kwargs={'station_id': station.id}))
            messages.error(request, str(station_form.errors))
        else:
            if station:
                station_form = StationRegistrationForm(instance=station)
            else:
                station_form = StationRegistrationForm()

        return render(
            request, 'base/station_register_step2.html', {
                'station_form': station_form,
                'client_id': client_id
            }
        )

    return redirect(reverse('base:home'))


def initialize_station_and_registration_status(request, station_id):
    """Return Station model and its registration status if station exists"""
    if station_id:
        station = get_object_or_404(
            Station.objects.prefetch_related(
                'antennas', 'antennas__antenna_type', 'antennas__frequency_ranges'
            ),
            id=station_id,
            owner=request.user
        )
        registered = bool(station.client_id)
        return (station, registered)
    return (None, False)


@login_required
def station_edit(request, station_id=None):
    """Edit or add a single station."""
    antenna_types = AntennaType.objects.all()
    frequency_range_formsets = {}
    antenna_formset = None

    (station, registered) = initialize_station_and_registration_status(request, station_id)

    if request.method == 'POST':
        validation_successful = False
        transaction_successful = False

        if station:
            station_form = StationForm(request.POST, request.FILES, instance=station)
        else:
            station_form = StationForm(request.POST, request.FILES)

        antenna_formset = AntennaInlineFormSet(
            request.POST, instance=station_form.instance, prefix='ant'
        )
        frequency_range_formsets = {}

        for antenna_form in antenna_formset:
            if not antenna_form['DELETE'].value():
                prefix = antenna_form.prefix
                frequency_range_formsets[prefix] = FrequencyRangeInlineFormSet(
                    request.POST, instance=antenna_form.instance, prefix=prefix + '-fr'
                )

        if station_form.is_valid():
            station = station_form.save(commit=False)
            station.owner = request.user
            if antenna_formset.is_valid():
                for frequency_range_formset in frequency_range_formsets:
                    if not frequency_range_formsets[frequency_range_formset].is_valid():
                        populate_formset_error_messages(
                            messages, request, frequency_range_formsets[frequency_range_formset]
                        )
                        break
                else:
                    validation_successful = True
            else:
                populate_formset_error_messages(messages, request, antenna_formset)
        else:
            messages.error(request, str(station_form.errors))

        if validation_successful:
            try:
                with transaction.atomic():
                    station.save()
                    antenna_formset.save()
                    for frequency_range_formset in frequency_range_formsets:
                        frequency_range_formsets[frequency_range_formset].save()
                    transaction_successful = True
            except DatabaseError:
                messages.error(
                    request, 'Something went worng, if the problem persists'
                    ' please contact an administrator'
                )

        if transaction_successful:
            messages.success(request, 'Ground Station {0} saved successfully.'.format(station.id))
            return redirect(reverse('base:station_view', kwargs={'station_id': station.id}))
        return render(
            request, 'base/station_edit.html', {
                'registered': registered,
                'station_form': station_form,
                'antenna_formset': antenna_formset,
                'frequency_range_formsets': frequency_range_formsets,
                'antenna_types': antenna_types,
                'max_antennas_per_station': settings.MAX_ANTENNAS_PER_STATION,
                'max_frequency_ranges_per_antenna': settings.MAX_FREQUENCY_RANGES_PER_ANTENNA,
                'max_frequency_for_range': settings.MAX_FREQUENCY_FOR_RANGE,
                'min_frequency_for_range': settings.MIN_FREQUENCY_FOR_RANGE,
                'vhf_min_frequency': settings.VHF_MIN_FREQUENCY,
                'vhf_max_frequency': settings.VHF_MAX_FREQUENCY,
                'uhf_min_frequency': settings.UHF_MIN_FREQUENCY,
                'uhf_max_frequency': settings.UHF_MAX_FREQUENCY,
                'l_min_frequency': settings.L_MIN_FREQUENCY,
                'l_max_frequency': settings.L_MAX_FREQUENCY,
                's_min_frequency': settings.S_MIN_FREQUENCY,
                's_max_frequency': settings.S_MAX_FREQUENCY,
                'image_changed': 'image' in station_form.changed_data,
            }
        )
    if station:
        station_form = StationForm(instance=station)
        antenna_formset = AntennaInlineFormSet(instance=station, prefix='ant')
        for antenna_form in antenna_formset.forms:
            antenna_prefix = antenna_form.prefix
            frequency_range_formsets[antenna_prefix] = FrequencyRangeInlineFormSet(
                instance=antenna_form.instance, prefix=antenna_prefix + '-fr'
            )
    else:
        station_form = StationForm()
        antenna_formset = AntennaInlineFormSet(prefix='ant')
    return render(
        request, 'base/station_edit.html', {
            'registered': registered,
            'station_form': station_form,
            'antenna_formset': antenna_formset,
            'frequency_range_formsets': frequency_range_formsets,
            'antenna_types': antenna_types,
            'max_antennas_per_station': settings.MAX_ANTENNAS_PER_STATION,
            'max_frequency_ranges_per_antenna': settings.MAX_FREQUENCY_RANGES_PER_ANTENNA,
            'max_frequency_for_range': settings.MAX_FREQUENCY_FOR_RANGE,
            'min_frequency_for_range': settings.MIN_FREQUENCY_FOR_RANGE,
            'vhf_min_frequency': settings.VHF_MIN_FREQUENCY,
            'vhf_max_frequency': settings.VHF_MAX_FREQUENCY,
            'uhf_min_frequency': settings.UHF_MIN_FREQUENCY,
            'uhf_max_frequency': settings.UHF_MAX_FREQUENCY,
            'l_min_frequency': settings.L_MIN_FREQUENCY,
            'l_max_frequency': settings.L_MAX_FREQUENCY,
            's_min_frequency': settings.S_MIN_FREQUENCY,
            's_max_frequency': settings.S_MAX_FREQUENCY,
        }
    )
