import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

EnvironmentKey = Literal["development", "production"]

FLAG_KEY_PATTERN = r"^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$"
FlagKey = Annotated[str, StringConstraints(pattern=FLAG_KEY_PATTERN, max_length=64)]

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _no_control_chars(value: str) -> str:
    if _CONTROL_CHARS.search(value):
        raise ValueError("must not contain control characters")
    return value


# Stable identifier of the end user being evaluated (opaque to FlagPilot).
UserId = Annotated[
    str, StringConstraints(min_length=1, max_length=256, strip_whitespace=False), AfterValidator(_no_control_chars)
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(BaseModel):
    code: str = Field(examples=["validation_error"])
    message: str
    details: list[dict] | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
