from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import get_engine


def test_live_is_ok(client):
    r = client.get("/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_ready_ok_when_dependencies_up(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok", "redis": "ok"}


def test_openapi_documents_core_endpoints(client):
    spec = client.get("/openapi.json").json()
    assert "/api/v1/evaluate" in spec["paths"]
    assert "/api/v1/admin/flags" in spec["paths"]
    assert client.get("/docs").status_code == 200


def test_models_match_migrations():
    """Fails if someone changes a model without writing a migration."""
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.check(cfg)


def test_environments_are_seeded():
    with get_engine().connect() as conn:
        keys = {r[0] for r in conn.execute(text("SELECT key FROM environments"))}
    assert keys == {"development", "production"}


def test_expected_indexes_and_uniques_exist():
    insp = inspect(get_engine())
    audit_idx = {i["name"] for i in insp.get_indexes("audit_events")}
    assert {"ix_audit_events_created_at", "ix_audit_events_flag_key_created_at"} <= audit_idx
    assert any(u["column_names"] == ["key"] for u in insp.get_unique_constraints("flags"))
    assert any(u["column_names"] == ["key_hash"] for u in insp.get_unique_constraints("api_keys"))


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO flags (id, key, name) VALUES (gen_random_uuid(), 'Bad Key!', 'n')",
        "INSERT INTO flags (id, key, name) VALUES (gen_random_uuid(), '-leading', 'n')",
        "INSERT INTO flags (id, key, name) VALUES (gen_random_uuid(), 'ok-key', '   ')",
    ],
)
def test_database_rejects_invalid_flags(app, sql):
    with pytest.raises(IntegrityError):
        with get_engine().begin() as conn:
            conn.execute(text(sql))


@pytest.mark.parametrize("pct", [-1, 101])
def test_database_rejects_out_of_range_rollout(app, admin, pct):
    admin.create_flag("db-check")
    with pytest.raises(IntegrityError):
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE flag_configs SET rollout_percentage = :p"), {"p": pct})


def test_database_rejects_duplicate_flag_key(app, admin):
    admin.create_flag("dupe")
    with pytest.raises(IntegrityError):
        with get_engine().begin() as conn:
            conn.execute(text("INSERT INTO flags (id, key, name) VALUES (gen_random_uuid(), 'dupe', 'again')"))


def test_database_rejects_non_array_targeting(app, admin):
    admin.create_flag("arr")
    with pytest.raises(IntegrityError):
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE flag_configs SET included_users = '{\"a\": 1}'::jsonb"))
