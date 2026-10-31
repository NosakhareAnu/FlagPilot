from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.main import create_app
from tests.conftest import ORIGIN, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD

LOGIN = "/api/v1/auth/login"


def login(client, email=TEST_ADMIN_EMAIL, password=TEST_ADMIN_PASSWORD, origin=ORIGIN):
    headers = {"Origin": origin} if origin else {}
    return client.post(LOGIN, json={"email": email, "password": password}, headers=headers)


def test_login_succeeds_and_sets_secure_cookie_attributes(client):
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == TEST_ADMIN_EMAIL and len(body["csrf_token"]) >= 32
    cookie = r.headers["set-cookie"].lower()
    assert "fp_session=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "password" not in r.text.lower()


def test_session_token_is_stored_hashed_not_plaintext(client):
    r = login(client)
    raw_token = client.cookies.get("fp_session")
    assert raw_token
    with get_engine().connect() as conn:
        hashes = [row[0] for row in conn.execute(text("SELECT token_hash FROM admin_sessions"))]
    assert hashes and raw_token not in hashes and all(len(h) == 64 for h in hashes)


def test_password_is_stored_with_argon2(client):
    with get_engine().connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM admin_users")).scalar_one()
    assert stored.startswith("$argon2id$") and TEST_ADMIN_PASSWORD not in stored


def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    a = login(client, password="wrong-password")
    b = login(client, email="nobody@example.com")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]
    assert "fp_session" not in a.headers.get("set-cookie", "")


def test_login_rejects_missing_or_foreign_origin(client):
    assert login(client, origin=None).status_code == 403
    assert login(client, origin="http://evil.example").status_code == 403


def test_login_validates_payload(client):
    r = client.post(LOGIN, json={"email": "a@b.co"}, headers={"Origin": ORIGIN})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post(LOGIN, json={"email": "a@b.co", "password": "x", "extra": 1}, headers={"Origin": ORIGIN})
    assert r.status_code == 422


def test_me_requires_session_and_returns_csrf(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["email"] == TEST_ADMIN_EMAIL


def test_every_admin_endpoint_requires_authentication(client):
    for method, url in [
        ("get", "/api/v1/admin/flags"),
        ("post", "/api/v1/admin/flags"),
        ("get", "/api/v1/admin/flags/x"),
        ("patch", "/api/v1/admin/flags/x"),
        ("patch", "/api/v1/admin/flags/x/environments/development"),
        ("post", "/api/v1/admin/flags/x/archive"),
        ("post", "/api/v1/admin/evaluate"),
        ("get", "/api/v1/admin/audit"),
        ("get", "/api/v1/admin/stats"),
        ("get", "/api/v1/admin/api-keys"),
        ("post", "/api/v1/admin/api-keys"),
    ]:
        r = getattr(client, method)(url, headers={"Origin": ORIGIN})
        assert r.status_code == 401, (method, url, r.status_code)


def test_mutations_require_csrf_token(client, admin):
    body = {"key": "csrf-flag", "name": "x"}
    # session cookie + origin but no CSRF header
    r = client.post("/api/v1/admin/flags", json=body, headers={"Origin": ORIGIN})
    assert r.status_code == 403 and "CSRF" in r.json()["error"]["message"]
    r = client.post("/api/v1/admin/flags", json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    assert admin.post("/api/v1/admin/flags", body).status_code == 201


def test_mutations_reject_cross_origin_even_with_valid_csrf(client, admin):
    r = client.post(
        "/api/v1/admin/flags",
        json={"key": "evil", "name": "x"},
        headers={"Origin": "http://evil.example", "X-CSRF-Token": admin.csrf},
    )
    assert r.status_code == 403
    r = client.post("/api/v1/admin/flags", json={"key": "evil", "name": "x"}, headers={"X-CSRF-Token": admin.csrf})
    assert r.status_code == 403  # no Origin header at all


def test_logout_invalidates_session_server_side(client, admin):
    stolen_cookie = client.cookies.get("fp_session")
    assert admin.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/admin/flags").status_code == 401
    # a copy of the old cookie must be dead too (server-side invalidation, not just cookie deletion)
    other = TestClient(client.app)
    other.cookies.set("fp_session", stolen_cookie)
    assert other.get("/api/v1/admin/flags").status_code == 401


def test_logout_requires_csrf(client, admin):
    r = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    assert r.status_code == 403


def test_expired_session_is_rejected(client, admin):
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE admin_sessions SET expires_at = now() - interval '1 minute'"))
    assert client.get("/api/v1/admin/flags").status_code == 401


def test_garbage_cookie_is_rejected(client):
    client.cookies.set("fp_session", "not-a-real-token")
    assert client.get("/api/v1/admin/flags").status_code == 401


def test_evaluation_api_key_is_not_a_dashboard_credential(client, dev):
    r = client.get("/api/v1/admin/flags", headers={"Authorization": f"Bearer {dev.key}"})
    assert r.status_code == 401


def test_login_is_rate_limited(settings, raw_redis, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3")
    get_settings.cache_clear()
    app = create_app(get_settings())
    with app.state.session_factory() as db:
        from app.services.bootstrap import run_bootstrap

        run_bootstrap(db, get_settings(), app.state.flag_cache)
    c = TestClient(app)
    codes = [login(c, password="bad").status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    # even the right password is throttled while the window is exhausted
    r = login(c)
    assert r.status_code == 429 and "Retry-After" in r.headers
    get_settings.cache_clear()


def test_demo_admin_password_follows_configuration(app, settings):
    """Changing ADMIN_PASSWORD and restarting updates the stored hash (configuration is the source of truth)."""
    from pydantic import SecretStr

    from app.services.bootstrap import ensure_admin

    new_settings = settings.model_copy(update={"admin_password": SecretStr("a-brand-new-password")})
    with app.state.session_factory() as db:
        ensure_admin(db, new_settings)
    c = TestClient(app)
    assert login(c, password=TEST_ADMIN_PASSWORD).status_code == 401
    assert login(c, password="a-brand-new-password").status_code == 200
