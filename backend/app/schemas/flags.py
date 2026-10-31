import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.common import EnvironmentKey, FlagKey, StrictModel, UserId

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]

MAX_TARGETED_USERS = 500


def _unique(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    if len(set(values)) != len(values):
        raise ValueError("duplicate user identifiers")
    return values


class FlagCreate(StrictModel):
    key: FlagKey = Field(description="Immutable unique key, lowercase letters, digits, '-' and '_'.", examples=["new-dashboard"])
    name: Name = Field(examples=["New dashboard"])
    description: Description = ""


class FlagUpdate(StrictModel):
    name: Name | None = None
    description: Description | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "FlagUpdate":
        if self.name is None and self.description is None:
            raise ValueError("provide at least one of: name, description")
        return self


class ConfigUpdate(StrictModel):
    """Partial update of one flag's configuration in one environment."""

    enabled: bool | None = None
    kill_switch: bool | None = None
    rollout_percentage: int | None = Field(default=None, ge=0, le=100)
    included_users: list[UserId] | None = Field(default=None, max_length=MAX_TARGETED_USERS)
    excluded_users: list[UserId] | None = Field(default=None, max_length=MAX_TARGETED_USERS)

    _uniq_inc = field_validator("included_users")(_unique)
    _uniq_exc = field_validator("excluded_users")(_unique)

    @model_validator(mode="after")
    def _at_least_one(self) -> "ConfigUpdate":
        if all(getattr(self, f) is None for f in type(self).model_fields):
            raise ValueError("provide at least one field to update")
        return self


class FlagConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    environment: EnvironmentKey
    enabled: bool
    kill_switch: bool
    rollout_percentage: int
    included_users: list[str]
    excluded_users: list[str]
    version: int
    updated_at: datetime


class FlagOut(BaseModel):
    key: str
    name: str
    description: str
    archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime = Field(description="Most recent change to the flag or any of its environment configs.")
    environments: dict[str, FlagConfigOut]


class FlagListOut(BaseModel):
    items: list[FlagOut]
    total: int


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor: str
    action: str
    flag_key: str | None
    environment: str | None
    details: dict


class AuditListOut(BaseModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


class EnvironmentStats(BaseModel):
    enabled: int
    disabled: int


class StatsOut(BaseModel):
    total_flags: int
    active_flags: int
    archived_flags: int
    environments: dict[str, EnvironmentStats]
    recent_events: list[AuditEventOut]


class ApiKeyCreate(StrictModel):
    name: Name
    environment: EnvironmentKey


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    environment: EnvironmentKey
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Full secret. Shown exactly once; only its SHA-256 hash is stored.")
