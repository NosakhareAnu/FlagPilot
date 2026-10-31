"""HTTP-level evaluation tests: API-key auth, environment isolation, targeting, and admin changes taking effect."""

import pytest

from tests.conftest import ORIGIN


def setup_flag(admin, key="new-dashboard", environment="development", **cfg):
    admin.create_flag(key)
    if cfg:
        assert admin.configure(key, environment, **cfg).status_code == 200


# ---------- authentication of evaluation clients ----------


def test_missing_authorization_is_401(client):
    r = client.post("/api/v1/evaluate", json={"flag_key": "x", "user_id": "u"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer not-a-key", "Basic abc", "Bearer fpk_development_short", "Bearer fpk_staging_" + "x" * 43],
)
def test_malformed_credentials_are_401(client, header):
    r = client.post("/api/v1/evaluate", json={"flag_key": "x", "user_id": "u"}, headers={"Authorization": header})
    assert r.status_code == 401


def test_well_formed_but_unknown_key_is_401(dev):
    assert dev.evaluate(key="fpk_development_" + "z" * 43).status_code == 401


def test_error_response_never_echoes_the_key(dev):
    bad = "fpk_development_" + "q" * 43
    assert bad not in dev.evaluate(key=bad).text


def test_dashboard_session_alone_cannot_evaluate(admin):
    r = admin.post("/api/v1/evaluate", {"flag_key": "x", "user_id": "u"})
    assert r.status_code == 401


def test_response_shape(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=100)
    r = dev.evaluate("new-dashboard", "alice")
    assert r.status_code == 200
    assert r.json() == {"flag_key": "new-dashboard", "enabled": True, "reason": "percentage_rollout", "environment": "development"}


# ---------- environment isolation ----------


def test_environment_is_determined_by_the_key(admin, dev, prod):
    setup_flag(admin, enabled=True, rollout_percentage=100)  # development only
    assert dev.evaluate().json()["enabled"] is True
    p = prod.evaluate().json()
    assert p["enabled"] is False and p["reason"] == "flag_disabled" and p["environment"] == "production"


def test_dev_key_cannot_read_production_config_by_any_request_field(admin, dev):
    setup_flag(admin, environment="production", enabled=True, rollout_percentage=100)
    # an "environment" field is not accepted: the key decides
    r = dev.evaluate(raw={"flag_key": "new-dashboard", "user_id": "u", "environment": "production"})
    assert r.status_code == 422
    r = dev.evaluate()
    assert r.json()["enabled"] is False and r.json()["environment"] == "development"


def test_changing_one_environment_does_not_change_the_other(admin, dev, prod):
    setup_flag(admin, enabled=True, rollout_percentage=100)
    admin.configure("new-dashboard", "production", enabled=True, rollout_percentage=100)
    admin.configure("new-dashboard", "production", enabled=False)
    assert dev.evaluate().json()["enabled"] is True
    assert prod.evaluate().json()["enabled"] is False


# ---------- evaluation semantics through the API ----------


def test_disabled_flag(admin, dev):
    setup_flag(admin)
    r = dev.evaluate().json()
    assert (r["enabled"], r["reason"]) == (False, "flag_disabled")


def test_zero_and_hundred_percent(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=0)
    users = [f"user-{i}" for i in range(60)]
    assert not any(dev.evaluate(user_id=u).json()["enabled"] for u in users)
    admin.configure("new-dashboard", enabled=True, rollout_percentage=100)
    assert all(dev.evaluate(user_id=u).json()["enabled"] for u in users)


def test_rollout_is_deterministic_and_monotonic_over_http(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=30)
    users = [f"u{i}" for i in range(120)]
    first = {u: dev.evaluate(user_id=u).json()["enabled"] for u in users}
    assert first == {u: dev.evaluate(user_id=u).json()["enabled"] for u in users}  # stable
    assert 0 < sum(first.values()) < len(users)
    admin.configure("new-dashboard", rollout_percentage=60)
    second = {u: dev.evaluate(user_id=u).json()["enabled"] for u in users}
    assert all(second[u] for u in users if first[u]), "raising the rollout removed an existing user"
    assert sum(second.values()) > sum(first.values())


def test_inclusion_exclusion_precedence(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=0, included_users=["vip"], excluded_users=["blocked"])
    assert dev.evaluate(user_id="vip").json() | {} == {
        "flag_key": "new-dashboard", "enabled": True, "reason": "user_included", "environment": "development"
    }
    assert dev.evaluate(user_id="blocked").json()["reason"] == "user_excluded"
    assert dev.evaluate(user_id="random").json()["reason"] == "default_disabled"
    admin.configure("new-dashboard", rollout_percentage=100)
    assert dev.evaluate(user_id="blocked").json()["enabled"] is False  # exclusion beats 100%
    assert dev.evaluate(user_id="vip").json()["reason"] == "user_included"
    assert dev.evaluate(user_id="random").json()["reason"] == "percentage_rollout"


def test_kill_switch_overrides_everything(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=100, included_users=["vip"])
    admin.configure("new-dashboard", kill_switch=True)
    for u in ("vip", "anyone"):
        r = dev.evaluate(user_id=u).json()
        assert (r["enabled"], r["reason"]) == (False, "kill_switch")
    admin.configure("new-dashboard", kill_switch=False)
    assert dev.evaluate(user_id="vip").json()["enabled"] is True


def test_unknown_flag_is_a_safe_disabled_response(dev):
    r = dev.evaluate("does-not-exist")
    assert r.status_code == 200
    assert r.json() == {"flag_key": "does-not-exist", "enabled": False, "reason": "flag_not_found", "environment": "development"}


def test_archived_flag_evaluates_disabled(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=100)
    assert dev.evaluate().json()["enabled"] is True
    admin.post("/api/v1/admin/flags/new-dashboard/archive")
    r = dev.evaluate().json()
    assert (r["enabled"], r["reason"]) == (False, "flag_archived")
    admin.post("/api/v1/admin/flags/new-dashboard/restore")
    assert dev.evaluate().json()["enabled"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"flag_key": "ok"},
        {"user_id": "u"},
        {"flag_key": "Bad Key", "user_id": "u"},
        {"flag_key": "ok", "user_id": ""},
        {"flag_key": "ok", "user_id": "x" * 257},
        {"flag_key": "ok", "user_id": "bad\x00id"},
        {"flag_key": "ok", "user_id": 123},
        {"flag_key": ["ok"], "user_id": "u"},
        {"flag_key": "ok", "user_id": "u", "extra": True},
    ],
)
def test_invalid_evaluation_requests_are_422(dev, payload):
    r = dev.evaluate(raw=payload)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_unusual_but_valid_user_ids(admin, dev):
    setup_flag(admin, enabled=True, rollout_percentage=50)
    for uid in ["ユーザー", "😀", "a" * 256, "user with spaces", "a@b.co", "../../etc/passwd", "' OR 1=1 --"]:
        assert dev.evaluate(user_id=uid).status_code == 200


# ---------- playground (admin) evaluation ----------


def test_playground_evaluate_uses_real_engine_for_any_environment(admin):
    setup_flag(admin, enabled=True, rollout_percentage=100)
    r = admin.post("/api/v1/admin/evaluate", {"flag_key": "new-dashboard", "environment": "development", "user_id": "alice"})
    body = r.json()
    assert r.status_code == 200 and body["enabled"] is True and body["reason"] == "percentage_rollout"
    assert body["rollout_percentage"] == 100 and 0 <= body["bucket"] < 10000
    r = admin.post("/api/v1/admin/evaluate", {"flag_key": "new-dashboard", "environment": "production", "user_id": "alice"})
    assert r.json()["enabled"] is False and r.json()["reason"] == "flag_disabled"
    assert admin.post("/api/v1/admin/evaluate", {"flag_key": "new-dashboard", "environment": "staging", "user_id": "a"}).status_code == 422


def test_playground_requires_csrf_and_session(client, dev):
    payload = {"flag_key": "x", "environment": "development", "user_id": "u"}
    assert client.post("/api/v1/admin/evaluate", json=payload, headers={"Origin": ORIGIN}).status_code == 401


# ---------- API keys ----------


def test_create_use_and_revoke_api_key(admin, client, dev):
    setup_flag(admin, enabled=True, rollout_percentage=100)
    created = admin.post("/api/v1/admin/api-keys", {"name": "Checkout service", "environment": "development"})
    assert created.status_code == 201
    body = created.json()
    secret = body["key"]
    assert secret.startswith("fpk_development_") and body["key_prefix"] == secret[: len(body["key_prefix"])]
    assert len(body["key_prefix"]) < len(secret)

    listed = admin.get("/api/v1/admin/api-keys").json()
    assert all("key" not in k or k.get("key") is None for k in listed)  # secrets are never listed
    assert secret not in str(listed)

    assert dev.evaluate(key=secret).json()["enabled"] is True  # works (and warms the key cache)
    assert admin.delete(f"/api/v1/admin/api-keys/{body['id']}").status_code == 200
    assert dev.evaluate(key=secret).status_code == 401  # revocation takes effect immediately, cache included
    assert admin.delete(f"/api/v1/admin/api-keys/{body['id']}").status_code == 409


def test_key_secret_is_only_stored_as_hash(admin, app):
    from sqlalchemy import text

    from app.db import get_engine

    secret = admin.post("/api/v1/admin/api-keys", {"name": "k", "environment": "production"}).json()["key"]
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT key_hash, key_prefix FROM api_keys")).all()
    assert all(secret not in (h, p) for h, p in rows)
    assert any(len(h) == 64 for h, _ in rows)


def test_api_key_validation(admin):
    assert admin.post("/api/v1/admin/api-keys", {"name": "", "environment": "development"}).status_code == 422
    assert admin.post("/api/v1/admin/api-keys", {"name": "x", "environment": "staging"}).status_code == 422
    assert admin.delete("/api/v1/admin/api-keys/not-a-uuid").status_code == 422
    assert admin.delete("/api/v1/admin/api-keys/00000000-0000-0000-0000-000000000000").status_code == 404
