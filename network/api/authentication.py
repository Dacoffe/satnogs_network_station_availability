"""SatNOGS Network API authentication, django rest framework"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from network.base.models import Station


class ClientIDAuthentication(BaseAuthentication):
    """
    Clients should authenticate by passing the Client ID in the "Authorization" HTTP header
    """

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth:
            return None

        if len(auth) > 1:
            msg = 'Invalid Client ID header. Token string should not contain spaces.'
            raise exceptions.AuthenticationFailed(msg)

        try:
            client_id = auth[0].decode()
        except UnicodeError:
            msg = 'Invalid Client ID. Client ID string should not contain invalid characters.'
            raise exceptions.AuthenticationFailed(msg)  # pylint: disable=W0707

        try:
            station = Station.objects.get(client_id=client_id)
        except Station.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid Client ID.')  # pylint: disable=W0707

        return (station.owner, client_id)


class ClientIDAuthenticationExtension(OpenApiAuthenticationExtension):
    """Extension for OpenAPI to support Client ID based authentication."""
    target_class = 'network.api.authentication.ClientIDAuthentication'
    name = 'ClientIDAuth'

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": (
                "Clients should authenticate by passing the"
                " Client ID in the 'Authorization' HTTP header"
            )
        }
