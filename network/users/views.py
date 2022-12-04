"""Django users views for SatNOGS Network"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.generic import RedirectView, UpdateView
from rest_framework.authtoken.models import Token

from network.base.models import Observation, Station
from network.base.perms import schedule_perms
from network.users.forms import UserForm
from network.users.models import User


class UserRedirectView(LoginRequiredMixin, RedirectView):
    """View for user redirect"""
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("users:view_user", kwargs={"username": self.request.user.username})


class UserUpdateView(LoginRequiredMixin, UpdateView):  # pylint: disable=R0901
    """View for user update"""
    form_class = UserForm

    model = User

    def get_success_url(self):
        return reverse("users:view_user", kwargs={"username": self.request.user.username})

    def get_object(self, queryset=None):
        return User.objects.get(username=self.request.user.username)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        print(settings.AUTH0, flush=True)
        context['auth0'] = settings.AUTH0
        return context


@login_required
def update_user_token(request):
    """View for API Key renewal"""
    token = Token.objects.filter(user=request.user)
    new_key = token[0].generate_key()
    token.update(key=new_key, created=now())

    return redirect(reverse("users:view_user", kwargs={"username": request.user.username}))


def view_user(request, username):
    """View for user page."""
    user = get_object_or_404(User, username=username)
    observations = Observation.objects.filter(
        author=user
    )[0:10].prefetch_related('satellite', 'ground_station')

    stations = Station.objects.filter(owner=user).annotate(
        total_obs=Count('observations'),
        future_obs=Count('pk', filter=Q(observations__end__gt=now())),
    ).prefetch_related('antennas', 'antennas__antenna_type', 'antennas__frequency_ranges')
    token = ''
    can_schedule = False
    if request.user.is_authenticated:
        can_schedule = schedule_perms(request.user)

        if request.user == user:
            try:
                token = Token.objects.get(user=user)
            except Token.DoesNotExist:
                token = Token.objects.create(user=user)

    return render(
        request, 'users/user_detail.html', {
            'user': user,
            'observations': observations,
            'stations': stations,
            'token': token,
            'can_schedule': can_schedule
        }
    )
