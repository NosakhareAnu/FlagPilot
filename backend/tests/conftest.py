"""Test fixtures. Tests run against REAL PostgreSQL and Redis from docker compose (no mocks):

  * database `flagpilot_test` (created on demand, schema built by running the real Alembic migrations)
  * Redis logical database 15 (flushed before every test)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

PG_USER = os.environ.get("POSTGRES_USER", "flagpilot")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
if not PG_PASSWORD:
    raise RuntimeError("POSTGRES_PASSWORD is not set: run `python scripts/setup.py` to create .env (the tests read it).")
PG_HOST = os.environ.get("TEST_PG_HOST", "127.0.0.1")
PG_PORT = os.environ.get("POSTGRES_PORT", "5432")
TEST_DB = "flagpilot_test"
TEST_DATABASE_URL = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{TEST_DB}"
TEST_REDIS_URL = f"redis://{os.environ.get('TEST_REDIS_HOST', '127.0.0.1')}:{os.environ.get('REDIS_PORT', '6379')}/15"

# Must be set BEFORE `app` modules read settings.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL

TEST_ADMIN_EMAIL = "admin@test.local"
TEST_ADMIN_PASSWORD = "correct horse battery staple"
TEST_DEV_KEY = "fpk_development_" + "d" * 43
TEST_PROD_KEY = "fpk_production_" + "p" * 43
ORIGIN = "http://localhost:3000"

os.environ.update(
    {
        "ADMIN_EMAIL": TEST_ADMIN_EMAIL,
        "ADMIN_PASSWORD": TEST_ADMIN_PASSWORD,
        "BOOTSTRAP_API_KEY_DEVELOPMENT": TEST_DEV_KEY,
        "BOOTSTRAP_API_KEY_PRODUCTION": TEST_PROD_KEY,
        "SEED_DEMO_DATA": "false",
        "CORS_ORIGINS": ORIGIN,
        "EVAL_RATE_LIMIT": "100000",
        "ADMIN_RATE_LIMIT": "100000",
        "LOGIN_RATE_LIMIT": "100000",
        "REDIS_RETRY_COOLDOWN": "0.3",
        "CACHE_TTL_SECONDS": "30",
        "LOG_LEVEL": "WARNING",
    }
)

import psycopg  # noqa: E402
import redis  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.bootstrap import run_bootstrap  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    admin_dsn = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/postgres"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    engine = get_engine()
    with engine.begin() as conn:  # start from a pristine schema, then run the real migrations
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def raw_redis() -> redis.Redis:
    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def app(settings, raw_redis):
    with get_engine().begin() as conn:
        conn.execute(
            text("TRUNCATE flags, flag_configs, audit_events, api_keys, admin_sessions, admin_users RESTART IDENTITY CASCADE")
        )
    application = create_app(settings)
    with application.state.session_factory() as db:
        run_bootstrap(db, settings, application.state.flag_cache)
    return application


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class AdminClient:
    """Logged-in dashboard client that behaves like the browser app: sends Origin + CSRF automatically."""

    def __init__(self, client: TestClient, csrf: str) -> None:
        self.http = client
        self.csrf = csrf

    def _headers(self, extra: dict | None = None) -> dict:
        return {"Origin": ORIGIN, "X-CSRF-Token": self.csrf, **(extra or {})}

    def get(self, url, **kw):
        return self.http.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.http.post(url, json=json, headers=self._headers(kw.pop("headers", None)), **kw)

    def patch(self, url, json=None, **kw):
        return self.http.patch(url, json=json, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.http.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)

    # --- convenience wrappers used throughout the suite ---
    def create_flag(self, key="new-dashboard", name="New dashboard", description="", **kw):
        return self.post("/api/v1/admin/flags", {"key": key, "name": name, "description": description}, **kw)

    def configure(self, key, environment="development", **fields):
        return self.patch(f"/api/v1/admin/flags/{key}/environments/{environment}", fields)


@pytest.fixture
def admin(client) -> AdminClient:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert r.status_code == 200, r.text
    return AdminClient(client, r.json()["csrf_token"])


class EvalClient:
    """Server-to-server client authenticated with an environment API key."""

    def __init__(self, client: TestClient, key: str) -> None:
        self.http = TestClient(client.app, raise_server_exceptions=False)  # separate cookie jar: no dashboard session
        self.key = key

    def evaluate(self, flag_key="new-dashboard", user_id="user-1", key=None, raw=None):
        headers = {"Authorization": f"Bearer {key or self.key}"}
        return self.http.post("/api/v1/evaluate", json=raw if raw is not None else {"flag_key": flag_key, "user_id": user_id}, headers=headers)


@pytest.fixture
def dev(client) -> EvalClient:
    return EvalClient(client, TEST_DEV_KEY)


@pytest.fixture
def prod(client) -> EvalClient:
    return EvalClient(client, TEST_PROD_KEY)
