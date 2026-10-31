"""Idempotent startup bootstrap: demo admin, environment API keys, optional demo flags."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import API_KEY_RE, hash_password, needs_rehash, sha256_hex, verify_password
from app.cache import FlagConfigCache
from app.config import Settings
from app.models import AdminUser, ApiKey, AuditEvent, Flag
from app.schemas.flags import ConfigUpdate, FlagCreate
from app.services.flags import FlagService

log = logging.getLogger("flagpilot.bootstrap")
BOOTSTRAP_KEY_NAME = "Bootstrap key"

DEMO_FLAGS = [
    # key, name, description, {environment: config}
    (
        "new-dashboard",
        "New analytics dashboard",
        "Redesigned analytics dashboard shown in the demo app. Roll out gradually, then flip on for everyone.",
        {
            "development": dict(enabled=True, rollout_percentage=50, included_users=["alice"], excluded_users=["dave"]),
            "production": dict(enabled=False),
        },
    ),
    (
        "dark-mode",
        "Dark mode",
        "Dark colour theme for the demo app.",
        {"development": dict(enabled=True, rollout_percentage=100), "production": dict(enabled=True, rollout_percentage=25)},
    ),
    (
        "ai-insights",
        "AI insights panel",
        "Experimental insights panel. Enabled for internal testers only.",
        {"development": dict(enabled=True, included_users=["alice", "bob"]), "production": dict(enabled=False)},
    ),
]


def ensure_admin(db: Session, settings: Settings) -> None:
    password = settings.admin_password.get_secret_value()
    if not password:
        log.warning("ADMIN_PASSWORD is not set; no administrator account was created")
        return
    email = settings.admin_email.strip().lower()
    user = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
    if user is None:
        db.add(AdminUser(email=email, password_hash=hash_password(password)))
        log.info("created demo administrator", extra={"email": email})
    elif not verify_password(user.password_hash, password) or needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)  # configuration is the source of truth
        log.info("updated demo administrator password from configuration")
    db.commit()


def ensure_api_keys(db: Session, settings: Settings) -> None:
    for environment, secret in (
        ("development", settings.bootstrap_api_key_development.get_secret_value()),
        ("production", settings.bootstrap_api_key_production.get_secret_value()),
    ):
        if not secret:
            continue
        match = API_KEY_RE.match(secret)
        if not match or match.group(1) != environment:
            log.error("ignoring malformed bootstrap API key", extra={"environment": environment})
            continue
        key_hash = sha256_hex(secret)
        # A rotated bootstrap secret revokes the previous bootstrap key for this environment.
        for old in db.execute(
            select(ApiKey).where(
                ApiKey.environment == environment, ApiKey.name == BOOTSTRAP_KEY_NAME, ApiKey.revoked_at.is_(None), ApiKey.key_hash != key_hash
            )
        ).scalars():
            old.revoked_at = datetime.now(UTC)
        existing = db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash)).scalar_one_or_none()
        if existing is None:
            prefix = secret[: len(f"fpk_{environment}_") + 6]
            db.add(ApiKey(name=BOOTSTRAP_KEY_NAME, environment=environment, key_prefix=prefix, key_hash=key_hash))
    db.commit()


def seed_demo_flags(db: Session, cache: FlagConfigCache) -> None:
    if db.execute(select(Flag.id).limit(1)).first() is not None:
        return
    svc = FlagService(db, cache, actor="system")
    for key, name, description, envs in DEMO_FLAGS:
        svc.create(FlagCreate(key=key, name=name, description=description))
        for environment, cfg in envs.items():
            svc.update_config(key, environment, ConfigUpdate(**cfg))
    log.info("seeded demo flags", extra={"count": len(DEMO_FLAGS)})


def run_bootstrap(db: Session, settings: Settings, cache: FlagConfigCache) -> None:
    try:
        ensure_admin(db, settings)
        ensure_api_keys(db, settings)
        if settings.seed_demo_data:
            seed_demo_flags(db, cache)
    except IntegrityError:
        db.rollback()  # another worker won the race; bootstrap is idempotent so this is fine
        log.info("bootstrap raced with another worker; continuing")


__all__ = ["run_bootstrap", "AuditEvent"]
