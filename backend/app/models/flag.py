import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ENVIRONMENT_KEYS = ("development", "production")


class Environment(Base):
    """Natural-key lookup table: 'development' and 'production' are seeded by the first migration."""

    __tablename__ = "environments"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Flag(Base):
    __tablename__ = "flags"
    __table_args__ = (
        CheckConstraint(r"key ~ '^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$'", name="ck_flags_key_format"),
        CheckConstraint("length(trim(name)) > 0", name="ck_flags_name_not_blank"),
        Index("ix_flags_archived_at", "archived_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    configs: Mapped[list["FlagConfig"]] = relationship(
        back_populates="flag", cascade="all, delete-orphan", order_by="FlagConfig.environment"
    )


class FlagConfig(Base):
    """Independent configuration of one flag in one environment."""

    __tablename__ = "flag_configs"
    __table_args__ = (
        CheckConstraint("rollout_percentage BETWEEN 0 AND 100", name="ck_flag_configs_rollout_range"),
        CheckConstraint("jsonb_typeof(included_users) = 'array'", name="ck_flag_configs_included_array"),
        CheckConstraint("jsonb_typeof(excluded_users) = 'array'", name="ck_flag_configs_excluded_array"),
    )

    flag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flags.id", ondelete="CASCADE"), primary_key=True
    )
    environment: Mapped[str] = mapped_column(String(32), ForeignKey("environments.key"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    kill_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rollout_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    included_users: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    excluded_users: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    flag: Mapped[Flag] = relationship(back_populates="configs")
