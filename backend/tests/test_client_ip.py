"""Client-IP resolution used by the rate limiters: spoofed X-Forwarded-For must not buy a fresh rate-limit bucket."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services.bootstrap import run_bootstrap
from tests.conftest import ORIGIN, TEST_ADMIN_EMAIL


def make_client(monkeypatch, hops: int, login_limit: int = 3) -> TestClient:
    monkeypatch.setenv("LOGIN_RATE_LIMIT", str(login_limit))
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", str(hops))
    get_settings.cache_clear()
    settings = get_settings()
    app = create_app(settings)
    with app.state.session_factory() as db:
        run_bootstrap(db, settings, app.state.flag_cache)
    return TestClient(app)


def attempt(client: TestClient, xff: str | None):
    headers = {"Origin": ORIGIN}
    if xff:
        headers["X-Forwarded-For"] = xff
    return client.post("/api/v1/auth/login", json={"email": TEST_ADMIN_EMAIL, "password": "wrong"}, headers=headers).status_code


def test_hops_zero_ignores_forwarded_header_entirely(app, monkeypatch):
    client = make_client(monkeypatch, hops=0)
    codes = [attempt(client, f"203.0.113.{i}") for i in range(5)]  # a different spoofed address every time
    assert codes == [401, 401, 401, 429, 429]
    get_settings.cache_clear()


def test_trusted_hop_uses_rightmost_entry_not_client_supplied_left_entries(app, monkeypatch):
    client = make_client(monkeypatch, hops=1)
    # an attacker prepends fake addresses; the trusted proxy appended the same real address each time
    codes = [attempt(client, f"203.0.113.{i}, 198.51.100.7") for i in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    get_settings.cache_clear()


def test_different_real_clients_behind_the_proxy_get_separate_buckets(app, monkeypatch):
    client = make_client(monkeypatch, hops=1)
    assert [attempt(client, "198.51.100.1") for _ in range(4)] == [401, 401, 401, 429]
    assert attempt(client, "198.51.100.2") == 401  # another real client is unaffected
    get_settings.cache_clear()


@pytest.mark.parametrize("header", [None, ""])
def test_missing_header_falls_back_to_peer_address(app, monkeypatch, header):
    client = make_client(monkeypatch, hops=1)
    assert [attempt(client, header) for _ in range(4)] == [401, 401, 401, 429]
    get_settings.cache_clear()
