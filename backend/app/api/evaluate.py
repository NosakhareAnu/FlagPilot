from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import ApiKeyContext, get_cache, require_api_key
from app.cache import FlagConfigCache
from app.db import get_db
from app.schemas.common import ErrorResponse
from app.schemas.evaluation import EvaluateRequest, EvaluateResponse
from app.services.evaluation import EvaluationService

router = APIRouter(prefix="/api/v1", tags=["evaluation"])

CACHE_HEADER = {"cache": "HIT", "database": "MISS", "database_cache_unavailable": "BYPASS"}


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    summary="Evaluate one feature flag for one user",
    responses={
        401: {"model": ErrorResponse, "description": "Missing, malformed, unknown or revoked API key"},
        422: {"model": ErrorResponse, "description": "Invalid request body"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded (see Retry-After)"},
        503: {"model": ErrorResponse, "description": "Evaluation temporarily unavailable. Clients should fail closed (treat the flag as off)."},
    },
)
def evaluate_flag(
    body: EvaluateRequest,
    response: Response,
    ctx: ApiKeyContext = Depends(require_api_key),
    db: Session = Depends(get_db),
    cache: FlagConfigCache = Depends(get_cache),
) -> EvaluateResponse:
    """Authenticate with ``Authorization: Bearer <environment API key>``. The environment is determined by the key,
    so a development key can never read production configuration.

    Safe defaults: an unknown flag returns ``enabled=false`` with reason ``flag_not_found`` (HTTP 200); an archived flag
    returns ``enabled=false`` with reason ``flag_archived``. If the database is unreachable and the answer is not
    cached, the API returns HTTP 503 rather than guessing.
    """
    outcome = EvaluationService(db, cache).evaluate(ctx.environment, body.flag_key, body.user_id)
    response.headers["X-FlagPilot-Cache"] = CACHE_HEADER[outcome.source]
    return EvaluateResponse(
        flag_key=body.flag_key,
        enabled=outcome.result.enabled,
        reason=outcome.result.reason,
        environment=ctx.environment,
    )
