"""Static defaults. Environment overrides are applied in app.client."""

BASE_TIMEOUT = 8          # seconds, for a single attempt
RETRY_BACKOFF_FACTOR = 2.5
DEFAULT_RETRIES = 3
LEGACY_TIMEOUT = 30       # pre-1.4 behaviour, kept for the deprecated v1 client
