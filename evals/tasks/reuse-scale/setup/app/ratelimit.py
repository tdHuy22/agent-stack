"""Giới hạn tốc độ theo key bằng cửa sổ trượt. Dùng lại được cho mọi route:

    limiter = SlidingWindowLimiter(limit=100, window_s=60)
    if not limiter.allow(key):
        raise HTTPException(status_code=429)
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window_s = window_s
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
