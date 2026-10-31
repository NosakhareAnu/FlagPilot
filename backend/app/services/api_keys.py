from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.auth.security import api_key_display_prefix, generate_api_key, sha256_hex
from app.cache import ApiKeyCache, FlagConfigCache  # noqa: F401
from app.models import ApiKey, AuditEvent
from app.repositories.auth import ApiKeyRepository
from app.schemas.flags import ApiKeyCreate
from app.services.errors import ConflictError, NotFoundError


class ApiKeyService:
    def __init__(self, db: Session, key_cache: ApiKeyCache, actor: str) -> None:
        self.db = db
        self.keys = ApiKeyRepository(db)
        self.key_cache = key_cache
        self.actor = actor

    def list(self) -> list[ApiKey]:
        return self.keys.list()

    def create(self, data: ApiKeyCreate) -> tuple[ApiKey, str]:
        secret = generate_api_key(data.environment)
        key = ApiKey(
            name=data.name,
            environment=data.environment,
            key_prefix=api_key_display_prefix(secret, data.environment),
            key_hash=sha256_hex(secret),
        )
        self.keys.add(key)
        self.db.add(
            AuditEvent(
                actor=self.actor,
                action="api_key.created",
                environment=data.environment,
                details={"name": data.name, "key_prefix": key.key_prefix},
            )
        )
        self.db.commit()
        return key, secret

    def revoke(self, key_id) -> ApiKey:
        key = self.keys.get(key_id)
        if key is None:
            raise NotFoundError("API key not found")
        if key.revoked_at is not None:
            raise ConflictError("API key is already revoked")
        key.revoked_at = datetime.now(UTC)
        self.db.add(
            AuditEvent(
                actor=self.actor,
                action="api_key.revoked",
                environment=key.environment,
                details={"name": key.name, "key_prefix": key.key_prefix},
            )
        )
        self.db.commit()
        self.key_cache.invalidate(key.key_hash)
        return key
