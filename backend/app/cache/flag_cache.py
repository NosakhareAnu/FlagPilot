"""Redis cache of per-(environment, flag) rule sets.

Strategy: cache-aside + TTL + explicit invalidation.
  * read:   GET fp:flag:{env}:{key}  -> hit returns immediately, miss falls through to PostgreSQL
  * write:  every admin change commits to PostgreSQL FIRST, then DELs the affected keys
  * safety: every entry has a TTL, so even if an invalidation is lost (Redis blip) staleness is bounded by the TTL
  * unknown flags are cached "negatively" with a shorter TTL so typos/probes cannot hammer the database
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from app.cache.guard import RedisGuard
from app.engine import FlagRuleSet
from app.models import ENVIRONMENT_KEYS

Status = Literal["hit", "miss", "bypass"]


@dataclass(frozen=True, slots=True)
class CacheLookup:
    status: Status  # hit | miss | bypass (Redis unavailable)
    found: bool = False  # for a hit: False means "negatively cached: flag does not exist"
    rules: FlagRuleSet | None = None


def flag_cache_key(environment: str, flag_key: str) -> str:
    return f"fp:flag:{environment}:{flag_key}"


def encode_rules(rules: FlagRuleSet) -> str:
    return json.dumps(
        {
            "found": True,
            "flag_key": rules.flag_key,
            "environment": rules.environment,
            "enabled": rules.enabled,
            "kill_switch": rules.kill_switch,
            "rollout_percentage": rules.rollout_percentage,
            "included_users": sorted(rules.included_users),
            "excluded_users": sorted(rules.excluded_users),
            "archived": rules.archived,
            "version": rules.version,
        },
        separators=(",", ":"),
    )


def decode_rules(raw: str | bytes) -> CacheLookup | None:
    try:
        data = json.loads(raw)
        if not data.get("found"):
            return CacheLookup("hit", found=False)
        rules = FlagRuleSet(
            flag_key=data["flag_key"],
            environment=data["environment"],
            enabled=bool(data["enabled"]),
            kill_switch=bool(data["kill_switch"]),
            rollout_percentage=int(data["rollout_percentage"]),
            included_users=frozenset(data["included_users"]),
            excluded_users=frozenset(data["excluded_users"]),
            archived=bool(data["archived"]),
            version=int(data["version"]),
        )
        return CacheLookup("hit", found=True, rules=rules)
    except (ValueError, KeyError, TypeError):
        return None  # corrupt entry -> treat as a miss


class FlagConfigCache:
    def __init__(self, guard: RedisGuard, ttl: int, negative_ttl: int) -> None:
        self.guard = guard
        self.ttl = ttl
        self.negative_ttl = negative_ttl
        guard.on_recover = self._purge_all

    @staticmethod
    def _purge_all(client) -> None:
        """After an outage some invalidations were skipped; drop every flag AND api-key entry (a revoked key must
        not stay valid in a Redis that comes back with its data intact)."""
        for pattern in ("fp:flag:*", "fp:apikey:*"):
            batch = []
            for key in client.scan_iter(match=pattern, count=500):
                batch.append(key)
                if len(batch) >= 500:
                    client.delete(*batch)
                    batch = []
            if batch:
                client.delete(*batch)

    def get(self, environment: str, flag_key: str) -> CacheLookup:
        if not self.guard.available:
            return CacheLookup("bypass")
        sentinel = object()
        raw = self.guard.call(lambda r: r.get(flag_cache_key(environment, flag_key)), sentinel)
        if raw is sentinel:
            return CacheLookup("bypass")
        if raw is None:
            return CacheLookup("miss")
        return decode_rules(raw) or CacheLookup("miss")

    def set(self, rules: FlagRuleSet) -> None:
        self.guard.call(
            lambda r: r.set(flag_cache_key(rules.environment, rules.flag_key), encode_rules(rules), ex=self.ttl), None
        )

    def set_missing(self, environment: str, flag_key: str) -> None:
        self.guard.call(
            lambda r: r.set(flag_cache_key(environment, flag_key), json.dumps({"found": False}), ex=self.negative_ttl),
            None,
        )

    def invalidate(self, flag_key: str, environments: tuple[str, ...] = ENVIRONMENT_KEYS) -> bool:
        """Delete cached entries for a flag. Returns False if Redis was unreachable (TTL then bounds staleness)."""
        keys = [flag_cache_key(env, flag_key) for env in environments]
        sentinel = object()
        return self.guard.call(lambda r: r.delete(*keys), sentinel) is not sentinel


class ApiKeyCache:
    """Caches valid API-key -> environment lookups so evaluation does not touch PostgreSQL per request."""

    def __init__(self, guard: RedisGuard, ttl: int = 60) -> None:
        self.guard = guard
        self.ttl = ttl

    @staticmethod
    def _key(key_hash: str) -> str:
        return f"fp:apikey:{key_hash}"

    def get(self, key_hash: str) -> dict | None:
        raw = self.guard.call(lambda r: r.get(self._key(key_hash)), None)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def set(self, key_hash: str, key_id: str, environment: str) -> None:
        payload = json.dumps({"id": key_id, "environment": environment})
        self.guard.call(lambda r: r.set(self._key(key_hash), payload, ex=self.ttl), None)

    def invalidate(self, key_hash: str) -> None:
        self.guard.call(lambda r: r.delete(self._key(key_hash)), None)
