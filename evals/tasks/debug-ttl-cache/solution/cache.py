"""Bộ nhớ đệm TTL + LRU."""
import time
from collections import OrderedDict

_MISSING = object()


class TTLCache:
    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("capacity phải >= 1")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl phải > 0")
        self.capacity = capacity
        self.ttl = ttl
        self._clock = clock
        self._data = OrderedDict()  # key -> (value, hạn hoặc None)
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    def _expired(self, entry):
        deadline = entry[1]
        return deadline is not None and self._clock() >= deadline

    def _deadline(self, ttl):
        ttl = self.ttl if ttl is None else ttl
        return None if ttl is None else self._clock() + ttl

    def _purge(self):
        for key in [k for k, e in self._data.items() if self._expired(e)]:
            del self._data[key]
            self.stats["expirations"] += 1

    def set(self, key, value, ttl=None):
        deadline = self._deadline(ttl)
        if key in self._data:
            self._data[key] = (value, deadline)
            self._data.move_to_end(key)
            return
        if len(self._data) >= self.capacity:
            self._purge()
        if len(self._data) >= self.capacity:
            self._data.popitem(last=False)
            self.stats["evictions"] += 1
        self._data[key] = (value, deadline)

    def _lookup(self, key):
        """Trả mục còn hạn hoặc None; mục hết hạn bị gỡ và tính một expiration."""
        entry = self._data.get(key)
        if entry is None:
            return None
        if self._expired(entry):
            del self._data[key]
            self.stats["expirations"] += 1
            return None
        return entry

    def get(self, key, default=None):
        entry = self._lookup(key)
        if entry is None:
            self.stats["misses"] += 1
            return default
        self._data.move_to_end(key)
        self.stats["hits"] += 1
        return entry[0]

    def pop(self, key, default=None):
        entry = self._lookup(key)
        if entry is None:
            return default
        del self._data[key]
        return entry[0]

    def get_or_load(self, key, loader):
        value = self.get(key, _MISSING)
        if value is not _MISSING:
            return value
        value = loader()
        self.set(key, value)
        return value

    def __contains__(self, key):
        entry = self._data.get(key)
        return entry is not None and not self._expired(entry)

    def __len__(self):
        return sum(1 for e in self._data.values() if not self._expired(e))
