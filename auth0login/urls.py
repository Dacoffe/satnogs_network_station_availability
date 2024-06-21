"""SatNOGS Network Auth0 login module URL routers"""
from django.urls import include, re_path

from . import views

urlpatterns = [
    re_path('^$', views.index),
    re_path(r'^', include(('django.contrib.auth.urls', 'auth'), namespace='auth')),
    re_path(r'^', include(('social_django.urls', 'social'), namespace='social')),
]
