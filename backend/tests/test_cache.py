"""Redis cache behaviour: population, invalidation, TTL safety net, outage fallback and recovery. Real Redis."""

import time

import redis
from sqlalchemy import text

from app.db import get_engine

KEY = "fp:flag:development:new-dashboard"


def cache_state(resp) -> str:
    return resp.headers["x-flagpilot-cache"]


def setup(admin, **cfg):
    admin.create_flag("new-dashboard")
    admin.configure("new-dashboard", "development", **cfg)


def test_first_evaluation_misses_then_hits(admin, dev, raw_redis):
    setup(admin, enabled=True, rollout_percentage=100)
    assert cache_state(dev.evaluate()) == "MISS"
    assert raw_redis.exists(KEY) == 1
    assert 0 < raw_redis.ttl(KEY) <= 30
    assert cache_state(dev.evaluate()) == "HIT"
    assert cache_state(dev.evaluate(user_id="someone-else")) == "HIT"  # cache is per flag+env, not per user


def test_cache_entry_never_contains_secrets_or_user_pii(admin, dev, raw_redis):
    setup(admin, enabled=True, included_users=["vip"])
    dev.evaluate(user_id="a-user-that-is-not-targeted")
    stored = raw_redis.get(KEY)
    assert "a-user-that-is-not-targeted" not in stored  # evaluated user ids are not cached
    assert "fpk_" not in str(raw_redis.keys("fp:flag:*"))


def test_environments_use_separate_cache_keys(admin, dev, prod, raw_redis):
    setup(admin, enabled=True, rollout_percentage=100)
    dev.evaluate()
    prod.evaluate()
    assert raw_redis.exists("fp:flag:development:new-dashboard") == 1
    assert raw_redis.exists("fp:flag:production:new-dashboard") == 1


def test_update_invalidates_only_the_changed_environment(admin, dev, prod, raw_redis):
    setup(admin, enabled=True, rollout_percentage=100)
    dev.evaluate()
    prod.evaluate()
    admin.configure("new-dashboard", "development", rollout_percentage=0)
    assert raw_redis.exists("fp:flag:development:new-dashboard") == 0
    assert raw_redis.exists("fp:flag:production:new-dashboard") == 1  # untouched


def test_changed_configuration_is_reflected_immediately_after_invalidation(admin, dev):
    setup(admin, enabled=True, rollout_percentage=100)
    assert dev.evaluate().json()["enabled"] is True and cache_state(dev.evaluate()) == "HIT"  # warm
    admin.configure("new-dashboard", "development", enabled=False)
    r = dev.evaluate()
    assert r.json()["enabled"] is False and r.json()["reason"] == "flag_disabled"
    assert cache_state(r) == "MISS"  # went back to PostgreSQL
    admin.configure("new-dashboard", "development", enabled=True, rollout_percentage=0, included_users=["u1"])
    assert dev.evaluate(user_id="u1").json()["reason"] == "user_included"
    assert dev.evaluate(user_id="u2").json()["reason"] == "default_disabled"


def test_every_kind_of_change_invalidates(admin, dev):
    setup(admin, enabled=True, rollout_percentage=100)
    for change, expected in [
        ({"kill_switch": True}, "kill_switch"),
        ({"kill_switch": False}, "percentage_rollout"),
        ({"excluded_users": ["u"]}, "user_excluded"),
        ({"excluded_users": []}, "percentage_rollout"),
        ({"rollout_percentage": 0}, "default_disabled"),
    ]:
        dev.evaluate()  # warm
        admin.configure("new-dashboard", "development", **change)
        assert dev.evaluate(user_id="u").json()["reason"] == expected, change


def test_archive_and_restore_invalidate_both_environments(admin, dev, prod):
    setup(admin, enabled=True, rollout_percentage=100)
    dev.evaluate()
    admin.post("/api/v1/admin/flags/new-dashboard/archive")
    assert dev.evaluate().json()["reason"] == "flag_archived"
    admin.post("/api/v1/admin/flags/new-dashboard/restore")
    assert dev.evaluate().json()["enabled"] is True


def test_unknown_flags_are_negatively_cached_and_creation_invalidates(admin, dev, raw_redis):
    assert dev.evaluate("late-flag").json()["reason"] == "flag_not_found"
    assert cache_state(dev.evaluate("late-flag")) == "HIT"  # negative entry
    assert 0 < raw_redis.ttl("fp:flag:development:late-flag") <= 10
    admin.create_flag("late-flag")
    admin.configure("late-flag", "development", enabled=True, rollout_percentage=100)
    assert dev.evaluate("late-flag").json()["enabled"] is True


def test_ttl_bounds_staleness_when_invalidation_is_lost(admin, dev, raw_redis):
    """Worst case: DB changed but the DEL never happened (e.g. Redis blip). The TTL guarantees eventual freshness."""
    setup(admin, enabled=True, rollout_percentage=100)
    assert dev.evaluate().json()["enabled"] is True
    with get_engine().begin() as conn:  # change the source of truth behind the cache's back
        conn.execute(text("UPDATE flag_configs SET enabled = false"))
    assert dev.evaluate().json()["enabled"] is True  # stale, but bounded...
    raw_redis.expire(KEY, 1)  # ...fast-forward the TTL instead of sleeping 30 s
    time.sleep(1.2)
    assert dev.evaluate().json() ["enabled"] is False


def test_corrupt_cache_entry_is_treated_as_a_miss(admin, dev, raw_redis):
    setup(admin, enabled=True, rollout_percentage=100)
    raw_redis.set(KEY, "{{{ definitely not json", ex=30)
    r = dev.evaluate()
    assert r.json()["enabled"] is True and cache_state(r) == "MISS"
    assert cache_state(dev.evaluate()) == "HIT"  # and it self-heals


def test_admin_playground_reports_cache_source(admin):
    setup(admin, enabled=True, rollout_percentage=100)
    body = {"flag_key": "new-dashboard", "environment": "development", "user_id": "u"}
    assert admin.post("/api/v1/admin/evaluate", body).json()["source"] == "database"
    assert admin.post("/api/v1/admin/evaluate", body).json()["source"] == "cache"


# ---------------- Redis outage & recovery ----------------


def dead_redis() -> redis.Redis:
    return redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.2, socket_connect_timeout=0.2, decode_responses=True)


def test_evaluation_survives_redis_outage_and_recovers(app, admin, dev, raw_redis):
    setup(admin, enabled=True, rollout_percentage=100)
    guard = app.state.redis_guard
    healthy_client = guard.client
    assert dev.evaluate().json()["enabled"] is True

    guard.client = dead_redis()  # --- outage ---
    r = dev.evaluate()
    assert r.status_code == 200 and r.json()["enabled"] is True
    assert cache_state(r) == "BYPASS"
    assert guard.failures >= 1 and not guard.available  # circuit open: next calls skip Redis instantly
    t0 = time.perf_counter()
    for _ in range(20):
        assert dev.evaluate().status_code == 200
    assert time.perf_counter() - t0 < 5  # no per-request timeout penalty while the circuit is open

    ready = app.state.redis_guard.client  # health is degraded, not down
    r = dev.http.get("/health/ready")
    assert r.status_code == 200 and r.json() == {"status": "degraded", "database": "ok", "redis": "unavailable"}

    # admin writes keep working during the outage and are visible to evaluation (no stale cache to serve)
    assert admin.configure("new-dashboard", "development", enabled=False).status_code == 200
    assert dev.evaluate().json()["reason"] == "flag_disabled"

    guard.client = healthy_client  # --- recovery ---
    time.sleep(0.4)  # cooldown (0.3 s in tests) elapses, next call probes Redis again
    assert cache_state(dev.evaluate()) == "MISS"  # reconnected, cache repopulated from PostgreSQL
    assert cache_state(dev.evaluate()) == "HIT"
    assert dev.http.get("/health/ready").json()["status"] == "ok"
    assert ready is not None


def test_invalidations_skipped_during_an_outage_are_reconciled_on_recovery(app, admin, dev, raw_redis):
    """Redis comes back still holding an entry whose DEL was skipped while it was unreachable.
    The guard's recovery hook purges flag entries, so the stale value is never served."""
    setup(admin, enabled=True, rollout_percentage=100)
    assert dev.evaluate().json()["enabled"] is True and raw_redis.exists(KEY)
    guard = app.state.redis_guard
    healthy = guard.client
    guard.client = dead_redis()
    admin.configure("new-dashboard", "development", enabled=False)  # DEL skipped: Redis unreachable
    assert raw_redis.exists(KEY) == 1  # the stale entry really is still there
    guard.client = healthy
    time.sleep(0.4)
    r = dev.evaluate()
    assert r.json()["enabled"] is False and r.json()["reason"] == "flag_disabled"
    assert cache_state(r) == "MISS"


def test_api_key_auth_still_works_during_redis_outage(app, dev):
    app.state.redis_guard.client = dead_redis()
    assert dev.evaluate("anything").status_code == 200


def test_health_reports_redis_down_without_failing(app, client):
    app.state.redis_guard.client = dead_redis()
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "degraded"
    assert client.get("/health/live").status_code == 200


def test_key_revoked_during_redis_outage_is_not_served_from_a_stale_key_cache_after_recovery(app, admin, dev, raw_redis):
    """Revocation's cache DEL is skipped while Redis is unreachable; the recovery purge must also clear API-key entries."""
    created = admin.post("/api/v1/admin/api-keys", {"name": "to-revoke", "environment": "development"}).json()
    assert dev.evaluate(key=created["key"]).status_code == 200  # warms fp:apikey:<hash>
    assert raw_redis.keys("fp:apikey:*")
    guard = app.state.redis_guard
    healthy = guard.client
    guard.client = dead_redis()
    assert admin.delete(f"/api/v1/admin/api-keys/{created['id']}").status_code == 200  # DEL skipped
    assert raw_redis.keys("fp:apikey:*")  # the stale 'valid' entry is still in Redis
    guard.client = healthy
    time.sleep(0.4)
    assert dev.evaluate(key=created["key"]).status_code == 401
