"""HTTP integration tests against the RUNNING docker compose stack (real containers, real network).

Skipped unless FLAGPILOT_LIVE_URL is set, e.g.:
    $env:FLAGPILOT_LIVE_URL = "http://127.0.0.1:8000"; python -m pytest tests/test_live_stack.py -v
Uses the credentials in the git-ignored root .env. Creates and archives its own uniquely named flag.
"""

import os
import time
from pathlib import Path

import httpx
import pytest

LIVE = os.environ.get("FLAGPILOT_LIVE_URL")
pytestmark = [pytest.mark.live, pytest.mark.skipif(not LIVE, reason="FLAGPILOT_LIVE_URL not set")]
ORIGIN = "http://localhost:3000"


def dotenv() -> dict[str, str]:
    out = {}
    for line in (Path(__file__).resolve().parents[2] / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


@pytest.fixture(scope="module")
def env():
    return dotenv()


@pytest.fixture(scope="module")
def admin(env):
    c = httpx.Client(base_url=LIVE, timeout=10)
    r = c.post("/api/v1/auth/login", json={"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]}, headers={"Origin": ORIGIN})
    assert r.status_code == 200, r.text
    c.headers.update({"Origin": ORIGIN, "X-CSRF-Token": r.json()["csrf_token"]})
    yield c
    c.close()


def test_live_health_is_ok():
    r = httpx.get(f"{LIVE}/health/ready", timeout=10)
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok", "redis": "ok"}


def test_live_full_flow(admin, env):
    key = f"live-{int(time.time())}"
    dev = {"Authorization": f"Bearer {env['BOOTSTRAP_API_KEY_DEVELOPMENT']}"}
    prod = {"Authorization": f"Bearer {env['BOOTSTRAP_API_KEY_PRODUCTION']}"}
    ev = lambda headers, user="u1": httpx.post(  # noqa: E731
        f"{LIVE}/api/v1/evaluate", json={"flag_key": key, "user_id": user}, headers=headers, timeout=10
    )
    try:
        assert admin.post("/api/v1/admin/flags", json={"key": key, "name": "Live test"}).status_code == 201
        assert ev(dev).json()["reason"] == "flag_disabled"
        assert admin.patch(f"/api/v1/admin/flags/{key}/environments/development", json={"enabled": True, "rollout_percentage": 100}).status_code == 200
        first, second = ev(dev), ev(dev)
        assert first.json()["enabled"] is True and second.headers["x-flagpilot-cache"] == "HIT"
        assert ev(prod).json() == {"flag_key": key, "enabled": False, "reason": "flag_disabled", "environment": "production"}
        admin.patch(f"/api/v1/admin/flags/{key}/environments/development", json={"rollout_percentage": 0})
        assert ev(dev).json()["enabled"] is False  # invalidation visible immediately across containers
        assert ev({"Authorization": "Bearer fpk_development_" + "x" * 43}).status_code == 401
    finally:
        admin.post(f"/api/v1/admin/flags/{key}/archive")
