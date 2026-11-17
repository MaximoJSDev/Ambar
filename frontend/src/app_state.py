"""Servicios compartidos por las vistas y los componentes de formularios."""

import logging

from api_client import ApiClient


# A single client keeps the login token and session-expiry state consistent across screens.
api = ApiClient()
log = logging.getLogger("sige.frontend")
