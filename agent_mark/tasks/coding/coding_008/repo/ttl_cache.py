"""An LRU cache whose entries also expire after a time-to-live."""

import time
from typing import Any, Callable


class TTLCache:
    """Least-recently-used cache with per-entry expiry.

    - ``capacity``: maximum number of live entries (>= 1, else ValueError).
    - ``ttl``: seconds an entry stays valid after it was last *set* (> 0, else ValueError).
    - ``clock``: zero-argument callable returning the current time in seconds;
      defaults to time.monotonic. Tests inject a fake clock.

    Semantics:
    - ``get(key, default=None)`` returns the value if present and not expired,
      and marks it most-recently-used. Expired entries are removed and treated
      as missing.
    - ``set(key, value)`` inserts or overwrites, resets the entry's TTL, and
      marks it most-recently-used. If this pushes the number of entries over
      capacity, expired entries are purged first; if still over capacity, the
      least-recently-used entry is evicted.
    - ``len(cache)`` is the number of non-expired entries.
    - ``key in cache`` is True only for non-expired entries and does NOT change
      recency.
    """

    def __init__(self, capacity: int, ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        raise NotImplementedError

    def get(self, key: Any, default: Any = None) -> Any:
        raise NotImplementedError

    def set(self, key: Any, value: Any) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __contains__(self, key: Any) -> bool:
        raise NotImplementedError
