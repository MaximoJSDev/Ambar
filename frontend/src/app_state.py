"""Process-wide services shared by views and form components."""

import logging

from api_client import ApiClient


# A single client keeps the login token and session-expiry state consistent across screens.
api = ApiClient()
log = logging.getLogger("sige.frontend")
