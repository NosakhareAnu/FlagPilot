"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
    )
    op.bulk_insert(
        sa.table("environments", sa.column("key", sa.String), sa.column("name", sa.String)),
        [{"key": "development", "name": "Development"}, {"key": "production", "name": "Production"}],
    )

    op.create_table(
        "flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(r"key ~ '^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$'", name="ck_flags_key_format"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_flags_name_not_blank"),
    )
    op.create_index("ix_flags_archived_at", "flags", ["archived_at"])

    op.create_table(
        "flag_configs",
        sa.Column("flag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("environment", sa.String(32), sa.ForeignKey("environments.key"), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("kill_switch", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("rollout_percentage", sa.Integer, nullable=False, server_default="0"),
        sa.Column("included_users", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("excluded_users", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rollout_percentage BETWEEN 0 AND 100", name="ck_flag_configs_rollout_range"),
        sa.CheckConstraint("jsonb_typeof(included_users) = 'array'", name="ck_flag_configs_included_array"),
        sa.CheckConstraint("jsonb_typeof(excluded_users) = 'array'", name="ck_flag_configs_excluded_array"),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "admin_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("environment", sa.String(32), sa.ForeignKey("environments.key"), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.String(254), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("flag_key", sa.String(64), nullable=True),
        sa.Column("environment", sa.String(32), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_flag_key_created_at", "audit_events", ["flag_key", "created_at"])


def downgrade() -> None:
    for table in ("audit_events", "api_keys", "admin_sessions", "admin_users", "flag_configs", "flags", "environments"):
        op.drop_table(table)
