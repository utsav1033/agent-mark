import os

from app import settings


def _resolve_timeout() -> float:
    env = os.environ.get("APP_TIMEOUT")
    if env is not None:
        return float(env)
    # Budget one full backoff window per request.
    return settings.BASE_TIMEOUT * settings.RETRY_BACKOFF_FACTOR


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.timeout = _resolve_timeout()
        self.retries = int(os.environ.get("APP_RETRIES", settings.DEFAULT_RETRIES))

    def get(self, path: str) -> str:
        raise NotImplementedError("network access is stubbed out in this repo")
