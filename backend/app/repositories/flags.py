from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import ENVIRONMENT_KEYS, AuditEvent, Flag, FlagConfig


class FlagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_key(self, key: str, *, for_update: bool = False) -> Flag | None:
        stmt = select(Flag).where(Flag.key == key).options(selectinload(Flag.configs))
        if for_update:
            stmt = stmt.with_for_update(of=Flag)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, *, include_archived: bool, search: str | None = None) -> list[Flag]:
        stmt = select(Flag).options(selectinload(Flag.configs)).order_by(Flag.created_at.desc(), Flag.key)
        if not include_archived:
            stmt = stmt.where(Flag.archived_at.is_(None))
        if search:
            escaped = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            stmt = stmt.where(func.lower(Flag.key).like(like, escape="\\") | func.lower(Flag.name).like(like, escape="\\"))
        return list(self.db.execute(stmt).scalars())

    def add_with_default_configs(self, flag: Flag) -> Flag:
        flag.configs = [FlagConfig(environment=env) for env in ENVIRONMENT_KEYS]
        self.db.add(flag)
        self.db.flush()
        return flag

    def get_config_for_evaluation(self, environment: str, flag_key: str) -> tuple[Flag, FlagConfig] | None:
        stmt = (
            select(Flag, FlagConfig)
            .join(FlagConfig, FlagConfig.flag_id == Flag.id)
            .where(Flag.key == flag_key, FlagConfig.environment == environment)
        )
        row = self.db.execute(stmt).first()
        return (row[0], row[1]) if row else None

    def counts(self) -> dict:
        total = self.db.scalar(select(func.count()).select_from(Flag)) or 0
        archived = self.db.scalar(select(func.count()).select_from(Flag).where(Flag.archived_at.is_not(None))) or 0
        env_rows = self.db.execute(
            select(FlagConfig.environment, FlagConfig.enabled, func.count())
            .join(Flag, Flag.id == FlagConfig.flag_id)
            .where(Flag.archived_at.is_(None))
            .group_by(FlagConfig.environment, FlagConfig.enabled)
        ).all()
        return {"total": total, "archived": archived, "env_rows": env_rows}


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, event: AuditEvent) -> None:
        self.db.add(event)

    def list(self, *, limit: int, offset: int, flag_key: str | None = None) -> tuple[list[AuditEvent], int]:
        base = select(AuditEvent)
        count = select(func.count()).select_from(AuditEvent)
        if flag_key:
            base = base.where(AuditEvent.flag_key == flag_key)
            count = count.where(AuditEvent.flag_key == flag_key)
        items = self.db.execute(base.order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit).offset(offset)).scalars()
        return list(items), self.db.scalar(count) or 0
