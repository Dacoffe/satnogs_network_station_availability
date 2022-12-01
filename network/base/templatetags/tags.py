"""Django template tags for SatNOGS Network"""
from hashlib import md5

from django import template
from django.urls import reverse

from network.base.utils import format_frequency

register = template.Library()


# TEMPLATE USE:  {{ email|gravatar_url:150 }}
@register.filter
def gravatar_url(email, size=40):
    """Returns the Gravatar URL based on user's email address"""
    return "https://www.gravatar.com/avatar/%s?s=%s" % (
        md5(email.lower().encode('utf-8')).hexdigest(), str(size)
    )


@register.simple_tag
def active(request, urls):
    """Returns if this is an active URL"""
    if request.path in (reverse(url) for url in urls.split()):
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


def get_demoddata_filenames(demoddata):
    """Returns the filename of a demoddata file"""
    if demoddata.payload_demod:
        return demoddata.payload_demod.name.split('/')[-1]
    return demoddata.demodulated_data.name.split('/')[-1]


@register.filter
def lookup_with_key(dictionary, key):
    """Returns a value from dictionary for a given key"""
    return dictionary.get(key)
