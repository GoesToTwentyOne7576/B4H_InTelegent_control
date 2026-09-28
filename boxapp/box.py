"""One shared box connection per process."""
from django.conf import settings

from .b4h import B4HClient

box = B4HClient(settings.B4H_BASE_URL, settings.B4H_USER, settings.B4H_PASS)
