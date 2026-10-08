"""Bộ nhớ đệm TTL + LRU."""
import time
from collections import OrderedDict

_MISSING = object()


class TTLCache:
    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("capacity phải >= 1")
        if ttl is not None and ttl < 0:
            raise ValueError("ttl phải > 0")
        self.capacity = capacity
        self.ttl = ttl
        self._clock = clock
        self._data = OrderedDict()  # key -> (value, hạn hoặc None)
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    def _expired(self, entry):
        deadline = entry[1]
        return deadline is not None and self._clock() > deadline

    def _deadline(self, ttl):
        ttl = self.ttl if ttl is None else ttl
        return None if ttl is None else self._clock() + ttl

    def set(self, key, value, ttl=None):
        if key in self._data:
            self._data[key] = (value, self._data[key][1])
            return
        if len(self._data) >= self.capacity:
            self._data.popitem(last=False)
            self.stats["evictions"] += 1
        self._data[key] = (value, self._deadline(ttl))

    def get(self, key, default=None):
        entry = self._data.get(key)
        if entry is None:
            self.stats["misses"] += 1
            return default
        if self._expired(entry):
            self.stats["expirations"] += 1
            self.stats["misses"] += 1
            return default
        self._data.move_to_end(key)
        self.stats["hits"] += 1
        return entry[0]

    def pop(self, key, default=None):
        entry = self._data.pop(key, None)
        if entry is None or self._expired(entry):
            return default
        return entry[0]

    def get_or_load(self, key, loader):
        value = self.get(key)
        if value:
            return value
        self._data[key] = (None, None)
        value = loader()
        self.set(key, value)
        return value

    def __contains__(self, key):
        return self.get(key, _MISSING) is not _MISSING

    def __len__(self):
        return len(self._data)
