from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text


router = APIRouter(prefix="/health", tags=["health"])


class LiveOut(BaseModel):
    status: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    database: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]


@router.get("/live", response_model=LiveOut)
def live() -> LiveOut:
    """Process is up. Does not touch dependencies (used by container health checks)."""
    return LiveOut(status="ok")


@router.get("/ready", response_model=ReadyOut, responses={503: {"model": ReadyOut}})
def ready(request: Request, response: Response) -> ReadyOut:
    """ok: everything works. degraded: Redis is down but requests are still served from PostgreSQL (200).
    unavailable: PostgreSQL is down, the platform cannot serve (503)."""
    db_ok = True
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    redis_ok = request.app.state.redis_guard.ping()
    status = "unavailable" if not db_ok else ("ok" if redis_ok else "degraded")
    if status == "unavailable":
        response.status_code = 503
    return ReadyOut(
        status=status, database="ok" if db_ok else "unavailable", redis="ok" if redis_ok else "unavailable"
    )
