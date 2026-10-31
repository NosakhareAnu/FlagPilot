"""Fixed-window rate limiter: Redis-backed (shared across workers) with an in-process fallback.

If Redis is down we do NOT fail open silently: the in-memory limiter keeps enforcing limits per process, which is
weaker across multiple workers but still bounds abuse.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.cache.guard import RedisGuard


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int  # seconds until the current window ends


class RateLimiter:
    def __init__(self, guard: RedisGuard, window_seconds: int = 60) -> None:
        self.guard = guard
        self.window = window_seconds
        self._mem: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def _window_index(self) -> tuple[int, int]:
        now = time.time()
        idx = int(now // self.window)
        return idx, max(1, int((idx + 1) * self.window - now))

    def hit(self, scope: str, ident: str, limit: int) -> RateLimitResult:
        """Count one request against (scope, ident) and report whether it is within ``limit`` per window."""
        idx, reset = self._window_index()
        key = f"fp:rl:{scope}:{ident}:{idx}"
        count = self.guard.call(lambda r: self._redis_incr(r, key), None)
        if count is None:
            count = self._mem_incr(key, idx)
        return RateLimitResult(count <= limit, limit, max(0, limit - count), reset)

    def count(self, scope: str, ident: str) -> int:
        """Current count without incrementing (used to throttle repeated authentication failures)."""
        idx, _ = self._window_index()
        key = f"fp:rl:{scope}:{ident}:{idx}"
        val = self.guard.call(lambda r: r.get(key), None)
        if val is not None:
            return int(val)
        with self._lock:
            entry = self._mem.get(key)
        return entry[1] if entry else 0

    def _redis_incr(self, r, key: str) -> int:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window + 1)
        return int(pipe.execute()[0])

    def _mem_incr(self, key: str, idx: int) -> int:
        with self._lock:
            if len(self._mem) > 10_000:  # drop expired windows
                self._mem = {k: v for k, v in self._mem.items() if v[0] >= idx}
            _, count = self._mem.get(key, (idx, 0))
            count += 1
            self._mem[key] = (idx, count)
            return count
