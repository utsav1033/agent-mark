"""An LRU cache whose entries also expire after a time-to-live."""

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    def __init__(self, capacity: int, ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if ttl <= 0:
            raise ValueError("ttl must be > 0")
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _expired(self, key: Any) -> bool:
        return self._data[key][1] <= self.clock()

    def _purge(self) -> None:
        for k in [k for k in self._data if self._expired(k)]:
            del self._data[k]

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default
        if self._expired(key):
            del self._data[key]
            return default
        self._data.move_to_end(key)
        return self._data[key][0]

    def set(self, key: Any, value: Any) -> None:
        self._data[key] = (value, self.clock() + self.ttl)
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            self._purge()
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        self._purge()
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        return key in self._data and not self._expired(key)
