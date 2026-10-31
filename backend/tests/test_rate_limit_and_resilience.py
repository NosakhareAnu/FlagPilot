"""Rate limiting, database failure handling, safe errors and log hygiene."""

import logging

import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.main import create_app
from app.services.bootstrap import run_bootstrap
from tests.conftest import ORIGIN, TEST_DEV_KEY, TEST_PROD_KEY, EvalClient, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD


def limited_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    get_settings.cache_clear()
    settings = get_settings()
    app = create_app(settings)
    with app.state.session_factory() as db:
        run_bootstrap(db, settings, app.state.flag_cache)
    return app


def test_evaluation_rate_limit_returns_429_with_headers(app, monkeypatch, raw_redis):
    app = limited_app(monkeypatch, EVAL_RATE_LIMIT=5)
    dev = EvalClient(TestClient(app), TEST_DEV_KEY)
    results = [dev.evaluate() for _ in range(8)]
    assert [r.status_code for r in results] == [200] * 5 + [429] * 3
    assert results[0].headers["x-ratelimit-limit"] == "5" and results[0].headers["x-ratelimit-remaining"] == "4"
    assert results[4].headers["x-ratelimit-remaining"] == "0"
    limited = results[5]
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["error"]["code"] == "rate_limited"
    get_settings.cache_clear()


def test_rate_limits_are_per_api_key(app, monkeypatch, raw_redis):
    app = limited_app(monkeypatch, EVAL_RATE_LIMIT=3)
    client = TestClient(app)
    dev, prod = EvalClient(client, TEST_DEV_KEY), EvalClient(client, TEST_PROD_KEY)
    assert [dev.evaluate().status_code for _ in range(4)] == [200, 200, 200, 429]
    assert prod.evaluate().status_code == 200  # a noisy neighbour doesn't consume another key's budget
    get_settings.cache_clear()


def test_rate_limit_still_enforced_when_redis_is_down(app, monkeypatch, raw_redis):
    app = limited_app(monkeypatch, EVAL_RATE_LIMIT=4)
    app.state.redis_guard.client = redis.Redis(host="127.0.0.1", port=1, socket_timeout=0.2, decode_responses=True)
    dev = EvalClient(TestClient(app), TEST_DEV_KEY)
    assert [dev.evaluate().status_code for _ in range(6)] == [200, 200, 200, 200, 429, 429]  # in-memory fallback
    get_settings.cache_clear()


def test_repeated_bad_credentials_are_throttled(app, dev):
    codes = [dev.evaluate(key=f"fpk_development_{i:043d}").status_code for i in range(40)]
    assert codes[:30] == [401] * 30
    assert set(codes[30:]) == {429}
    # while throttled, even a valid key from the same client IP is refused: the throttle is checked first
    assert dev.evaluate().status_code == 429


def test_admin_rate_limit(app, monkeypatch, raw_redis):
    app = limited_app(monkeypatch, ADMIN_RATE_LIMIT=4)
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD}, headers={"Origin": ORIGIN})
    assert r.status_code == 200
    codes = [c.get("/api/v1/admin/stats").status_code for _ in range(6)]
    assert codes == [200, 200, 200, 200, 429, 429]
    get_settings.cache_clear()


# ---------------- database failure ----------------


def break_database(app):
    dead = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    healthy = app.state.session_factory
    app.state.session_factory = sessionmaker(bind=dead, expire_on_commit=False, autoflush=False)
    return healthy


def test_database_outage_gives_503_not_a_stack_trace(app, admin, dev):
    admin.create_flag("db-down")
    break_database(app)
    r = dev.evaluate("db-down-uncached")
    assert r.status_code == 503
    assert r.json()["error"]["code"] in {"database_unavailable", "database_error"}
    assert "Traceback" not in r.text and "psycopg" not in r.text and "postgresql" not in r.text
    assert r.headers.get("retry-after") == "5" or r.json()["error"]["code"] == "database_error"


def test_database_outage_admin_and_readiness(app, admin, client):
    break_database(app)
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/ready").json() == {"status": "unavailable", "database": "unavailable", "redis": "ok"}
    assert client.get("/health/live").status_code == 200  # process is alive even though not ready
    r = client.get("/api/v1/auth/me")  # session lookup needs the DB
    assert r.status_code == 503


def test_cached_flags_keep_working_during_database_outage(app, admin, dev):
    admin.create_flag("resilient")
    admin.configure("resilient", "development", enabled=True, rollout_percentage=100)
    assert dev.evaluate("resilient").json()["enabled"] is True  # warms Redis (+ API-key cache)
    break_database(app)
    r = dev.evaluate("resilient")  # API key + flag config both served from Redis
    assert r.status_code == 200 and r.json()["enabled"] is True and r.headers["x-flagpilot-cache"] == "HIT"


def test_service_recovers_after_database_returns(app, admin, dev):
    healthy = break_database(app)
    assert dev.evaluate("recovering").status_code in (200, 503)
    app.state.session_factory = healthy
    assert dev.evaluate("recovering").status_code == 200


# ---------------- safe errors & log hygiene ----------------


def test_unhandled_exception_returns_generic_500(app, client):
    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail fpk_development_leak")

    r = client.get("/boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in r.text and "fpk_" not in r.text


def test_cors_allows_only_configured_origin(client):
    ok = client.options(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-csrf-token"},
    )
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    assert ok.headers.get("access-control-allow-credentials") == "true"
    bad = client.options(
        "/api/v1/auth/login", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in bad.headers


def test_security_headers_and_request_id(client):
    r = client.get("/health/live", headers={"X-Request-ID": "trace-123"})
    assert r.headers["x-request-id"] == "trace-123"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/v1/auth/me").headers["cache-control"] == "no-store"


def test_secrets_never_appear_in_logs(app, admin, dev, caplog):
    caplog.set_level(logging.DEBUG)
    dev.evaluate()
    dev.evaluate(key="fpk_development_" + "n" * 43)
    admin.post("/api/v1/auth/logout")
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"email": TEST_ADMIN_EMAIL, "password": "wrong-but-memorable-pw"}, headers={"Origin": ORIGIN})
    log_text = "\n".join(f"{r.getMessage()} {getattr(r, '__dict__', '')}" for r in caplog.records)
    for secret in (TEST_DEV_KEY, TEST_PROD_KEY, TEST_ADMIN_PASSWORD, "wrong-but-memorable-pw", admin.csrf, "fpk_development_" + "n" * 43):
        assert secret not in log_text
