"""Django template tags for SatNOGS Network"""
from hashlib import md5

from django import template
from django.conf import settings
from django.urls import reverse

from network.base.utils import format_frequency

register = template.Library()


@register.simple_tag
def satnogs_db_url():
    """
    Returns the configured SatNOGS DB URL

    Usage:
        {% satnogs_db_url %}
    """

    # Drop path from URL (usually 'api/')
    satnogs_db_base_url = settings.DB_API_ENDPOINT.rstrip('/')[:-3]

    return satnogs_db_base_url


# TEMPLATE USE:  {{ email|gravatar_url:150 }}
@register.filter
def gravatar_url(email, size=40):
    """Returns the Gravatar URL based on user's email address"""
    return "https://www.gravatar.com/avatar/%s?s=%s" % (
        md5(email.lower().encode('utf-8')).hexdigest(), str(size)
    )


@register.filter
def get_item(dictionary, key):
    """Acesses a key of a dictionary. Used when the key is a variable"""
    return dictionary.get(key)


@register.filter(name='not_true')
def not_true(value):
    """A filter to be used as a not-equals operator"""
    return not value


@register.simple_tag
def active(request, urls):
    """Returns if this is an active URL"""
    if hasattr(request, 'path') and request.path in (reverse(url) for url in urls.split()):
        return 'active'
    return None


@register.simple_tag
def drifted_frq(value, drift):
    """Returns drifred frequency"""
    return int(round(value + ((value * drift) / 1e9)))


@register.filter
def sort_types(types):
    """Returns sorted 'Other' antenna types"""
    other = []
    sorted_types = []
    for antenna_type in types:
        if 'Other' in antenna_type.name:
            other.append(antenna_type)
            continue
        sorted_types.append(antenna_type)
    return sorted_types + other


@register.filter
def frq(value):
    """Returns Hz formatted frequency html string"""
    return format_frequency(value)


@register.filter
def percentagerest(value):
    """Returns the rest of percentage from a given (percentage) value"""
    try:
        return 100 - value
    except (TypeError, ValueError):
        return 0


@register.filter
def lookup_with_key(dictionary, key):
    """Returns a value from dictionary for a given key"""
    return dictionary.get(key)
