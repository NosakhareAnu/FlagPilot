from typing import Literal

from pydantic import BaseModel, Field

from app.engine import Reason
from app.schemas.common import EnvironmentKey, FlagKey, StrictModel, UserId


class EvaluateRequest(StrictModel):
    flag_key: FlagKey = Field(examples=["new-dashboard"])
    user_id: UserId = Field(description="Stable identifier of the end user (opaque to FlagPilot).", examples=["user-1842"])


class EvaluateResponse(BaseModel):
    flag_key: str
    enabled: bool
    reason: Reason = Field(description="Why this result was produced (see evaluation precedence in the docs).")
    environment: EnvironmentKey = Field(description="Environment resolved from the API key.")


class AdminEvaluateRequest(EvaluateRequest):
    environment: EnvironmentKey


class AdminEvaluateResponse(EvaluateResponse):
    """Playground response: adds debugging details that are not sent to evaluation clients."""

    bucket: int | None = Field(default=None, description="User's rollout bucket in [0, 10000), when computed.")
    rollout_percentage: int | None = None
    source: Literal["cache", "database", "database_cache_unavailable"]
