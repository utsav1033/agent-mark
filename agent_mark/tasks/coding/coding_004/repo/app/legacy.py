"""Deprecated v1 client. Not used by HttpClient."""

from app import settings


class LegacyClient:
    timeout = settings.LEGACY_TIMEOUT
