from pydantic import SecretStr
from sqlalchemy import text

from app.db import get_engine
from app.services.bootstrap import ensure_admin, ensure_api_keys
from tests.conftest import TEST_DEV_KEY, TEST_PROD_KEY


def active_keys():
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT environment, key_hash FROM api_keys WHERE revoked_at IS NULL")).all()


def test_bootstrap_is_idempotent(app, settings):
    with app.state.session_factory() as db:
        for _ in range(3):
            ensure_admin(db, settings)
            ensure_api_keys(db, settings)
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM admin_users")).scalar_one() == 1
    assert sorted(e for e, _ in active_keys()) == ["development", "production"]


def test_rotating_bootstrap_key_revokes_the_old_one(app, settings, dev):
    new_key = "fpk_development_" + "r" * 43
    rotated = settings.model_copy(update={"bootstrap_api_key_development": SecretStr(new_key)})
    with app.state.session_factory() as db:
        ensure_api_keys(db, rotated)
    assert dev.evaluate(key=new_key).status_code == 200
    assert dev.evaluate(key=TEST_DEV_KEY).status_code == 401


def test_malformed_or_wrong_environment_bootstrap_keys_are_ignored(app, settings):
    bad = settings.model_copy(
        update={
            "bootstrap_api_key_development": SecretStr(TEST_PROD_KEY),  # production-format key in the dev slot
            "bootstrap_api_key_production": SecretStr("tooshort"),
        }
    )
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM api_keys"))
    with app.state.session_factory() as db:
        ensure_api_keys(db, bad)
    assert active_keys() == []


def test_no_admin_created_without_password(app, settings):
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM admin_users"))
    with app.state.session_factory() as db:
        ensure_admin(db, settings.model_copy(update={"admin_password": SecretStr("")}))
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM admin_users")).scalar_one() == 0
