"""Circuit-breaker wrapper around a Redis client.

Redis is an optimisation, never a dependency for correctness. Every Redis call goes through ``RedisGuard.call``:
on any Redis/network error we log once, open the circuit for ``cooldown`` seconds (calls are skipped instantly, so a dead
Redis adds no latency), then let the next call probe again ("half-open"). That probe is the recovery path.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import redis
from redis.exceptions import RedisError

log = logging.getLogger("flagpilot.redis")
T = TypeVar("T")


class RedisGuard:
    def __init__(self, client: redis.Redis, cooldown: float = 5.0) -> None:
        self.client = client
        self.cooldown = cooldown
        self._open_until = 0.0
        self._needs_reconcile = False
        self.failures = 0
        # Runs once after Redis comes back from a failure. While it was unreachable, invalidations may have been
        # skipped, so the cache layer uses this hook to drop everything it might still hold (see FlagConfigCache).
        self.on_recover: Callable[[redis.Redis], None] | None = None

    @property
    def available(self) -> bool:
        """False while the circuit is open (Redis recently failed)."""
        return time.monotonic() >= self._open_until

    def call(self, fn: Callable[[redis.Redis], T], default: T) -> T:
        if not self.available:
            return default
        try:
            if self._needs_reconcile and self.on_recover is not None:
                self.on_recover(self.client)
                log.info("redis recovered; stale cache entries purged")
            self._needs_reconcile = False
            result = fn(self.client)
        except (RedisError, OSError) as exc:
            self.failures += 1
            self._needs_reconcile = True
            self._open_until = time.monotonic() + self.cooldown
            log.warning("redis unavailable, falling back to database", extra={"error": type(exc).__name__})
            return default
        return result

    def ping(self) -> bool:
        """Health probe that ignores the open circuit so /health/ready reflects reality."""
        try:
            ok = bool(self.client.ping())
        except (RedisError, OSError):
            return False
        if ok:
            self._open_until = 0.0
        return ok
