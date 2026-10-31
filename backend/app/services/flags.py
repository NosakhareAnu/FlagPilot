"""Flag management use-cases. Every change is audited in the same transaction, then the cache is invalidated."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.cache import FlagConfigCache
from app.models import AuditEvent, Flag, FlagConfig
from app.repositories.flags import AuditRepository, FlagRepository
from app.schemas.flags import ConfigUpdate, FlagConfigOut, FlagCreate, FlagOut, FlagUpdate
from app.services.errors import ConflictError, NotFoundError, UnprocessableError

log = logging.getLogger("flagpilot.flags")


def to_flag_out(flag: Flag) -> FlagOut:
    configs = {c.environment: FlagConfigOut.model_validate(c) for c in flag.configs}
    latest = max([flag.updated_at, *(c.updated_at for c in flag.configs)])
    return FlagOut(
        key=flag.key,
        name=flag.name,
        description=flag.description,
        archived=flag.archived_at is not None,
        archived_at=flag.archived_at,
        created_at=flag.created_at,
        updated_at=latest,
        environments=configs,
    )


class FlagService:
    def __init__(self, db: Session, cache: FlagConfigCache, actor: str) -> None:
        self.db = db
        self.cache = cache
        self.actor = actor
        self.flags = FlagRepository(db)
        self.audit = AuditRepository(db)

    # ----- helpers -----
    def _audit(self, action: str, flag_key: str | None, environment: str | None = None, **details) -> None:
        self.audit.add(
            AuditEvent(actor=self.actor, action=action, flag_key=flag_key, environment=environment, details=details)
        )

    def _require(self, key: str, *, for_update: bool = False) -> Flag:
        flag = self.flags.get_by_key(key, for_update=for_update)
        if flag is None:
            raise NotFoundError(f"Flag '{key}' does not exist")
        return flag

    def _commit_and_invalidate(self, flag_key: str, environments: tuple[str, ...] | None = None) -> None:
        self.db.commit()  # source of truth first ...
        ok = self.cache.invalidate(flag_key) if environments is None else self.cache.invalidate(flag_key, environments)
        if not ok:
            log.warning("cache invalidation skipped (redis unavailable); TTL bounds staleness", extra={"flag_key": flag_key})

    # ----- queries -----
    def list(self, *, include_archived: bool = False, search: str | None = None) -> list[Flag]:
        return self.flags.list(include_archived=include_archived, search=search)

    def get(self, key: str) -> Flag:
        return self._require(key)

    # ----- commands -----
    def create(self, data: FlagCreate) -> Flag:
        flag = Flag(key=data.key, name=data.name, description=data.description)
        try:
            self.flags.add_with_default_configs(flag)
            self._audit("flag.created", flag.key, name=flag.name, description=flag.description)
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(f"A flag with key '{data.key}' already exists") from exc
        self._commit_and_invalidate(flag.key)  # clears any negative-cache entry for this key
        return self._require(flag.key)

    def update_metadata(self, key: str, data: FlagUpdate) -> Flag:
        flag = self._require(key, for_update=True)
        changes: dict[str, dict[str, str]] = {}
        if data.name is not None and data.name != flag.name:
            changes["name"] = {"from": flag.name, "to": data.name}
            flag.name = data.name
        if data.description is not None and data.description != flag.description:
            changes["description"] = {"from": flag.description, "to": data.description}
            flag.description = data.description
        if changes:
            flag.updated_at = datetime.now(UTC)
            self._audit("flag.updated", key, changes=changes)
            self.db.commit()
        return self._require(key)

    def update_config(self, key: str, environment: str, patch: ConfigUpdate) -> Flag:
        flag = self._require(key, for_update=True)
        if flag.archived_at is not None:
            raise ConflictError("Archived flags cannot be modified. Restore the flag first.")
        cfg = next((c for c in flag.configs if c.environment == environment), None)
        if cfg is None:  # unreachable while environments are fixed, but keep a clean error
            raise NotFoundError(f"Environment '{environment}' does not exist")

        changes = patch.model_dump(exclude_none=True)
        included = changes.get("included_users", cfg.included_users)
        excluded = changes.get("excluded_users", cfg.excluded_users)
        overlap = sorted(set(included) & set(excluded))
        if overlap:
            raise UnprocessableError(f"Users cannot be both included and excluded: {', '.join(overlap[:5])}")

        events = self._diff(cfg, changes)
        if not events:
            return flag  # idempotent no-op: no version bump, no audit noise

        for field, value in changes.items():
            setattr(cfg, field, value)
        cfg.version += 1
        now = datetime.now(UTC)
        cfg.updated_at = now
        flag.updated_at = now
        for action, details in events:
            self._audit(action, key, environment, **details)
        self._commit_and_invalidate(key, (environment,))  # only this environment's cache entry is affected
        return self._require(key)

    @staticmethod
    def _diff(cfg: FlagConfig, changes: dict) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        if "enabled" in changes and changes["enabled"] != cfg.enabled:
            events.append(("flag.enabled" if changes["enabled"] else "flag.disabled", {"from": cfg.enabled, "to": changes["enabled"]}))
        if "kill_switch" in changes and changes["kill_switch"] != cfg.kill_switch:
            events.append(
                ("flag.kill_switch_activated" if changes["kill_switch"] else "flag.kill_switch_cleared", {"from": cfg.kill_switch, "to": changes["kill_switch"]})
            )
        if "rollout_percentage" in changes and changes["rollout_percentage"] != cfg.rollout_percentage:
            events.append(("flag.rollout_changed", {"from": cfg.rollout_percentage, "to": changes["rollout_percentage"]}))
        targeting: dict[str, list[str]] = {}
        for field in ("included_users", "excluded_users"):
            if field in changes and set(changes[field]) != set(getattr(cfg, field)):
                old, new = set(getattr(cfg, field)), set(changes[field])
                targeting[f"{field.split('_')[0]}_added"] = sorted(new - old)
                targeting[f"{field.split('_')[0]}_removed"] = sorted(old - new)
        if targeting:
            events.append(("flag.targeting_updated", targeting))
        return events

    def archive(self, key: str) -> Flag:
        flag = self._require(key, for_update=True)
        if flag.archived_at is not None:
            raise ConflictError(f"Flag '{key}' is already archived")
        flag.archived_at = flag.updated_at = datetime.now(UTC)
        self._audit("flag.archived", key)
        self._commit_and_invalidate(key)
        return self._require(key)

    def restore(self, key: str) -> Flag:
        flag = self._require(key, for_update=True)
        if flag.archived_at is None:
            raise ConflictError(f"Flag '{key}' is not archived")
        flag.archived_at = None
        flag.updated_at = datetime.now(UTC)
        self._audit("flag.restored", key)
        self._commit_and_invalidate(key)
        return self._require(key)
