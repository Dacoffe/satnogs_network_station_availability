"""Custom renderers for SatNOGS API"""

from rest_framework.renderers import BrowsableAPIRenderer


class BrowsableAPIRendererWithoutForms(BrowsableAPIRenderer):
    """Renders the browsable api, but excludes the forms."""
    def show_form_for_method(self, view, method, request, obj):
        return False
