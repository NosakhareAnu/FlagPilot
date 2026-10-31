"""Administrator (dashboard) API. Every route requires a valid session; unsafe methods also need CSRF + Origin."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import AdminContext, get_cache, get_key_cache, require_admin
from app.cache import ApiKeyCache, FlagConfigCache
from app.db import get_db
from app.repositories.flags import AuditRepository
from app.schemas.common import EnvironmentKey, ErrorResponse, FlagKey
from app.schemas.evaluation import AdminEvaluateRequest, AdminEvaluateResponse
from app.schemas.flags import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    AuditEventOut,
    AuditListOut,
    ConfigUpdate,
    FlagCreate,
    FlagListOut,
    FlagOut,
    FlagUpdate,
    StatsOut,
)
from app.services.api_keys import ApiKeyService
from app.services.evaluation import EvaluationService
from app.services.flags import FlagService, to_flag_out
from app.services.stats import build_stats

ERRORS = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)], responses=ERRORS)

Admin = Annotated[AdminContext, Depends(require_admin)]
DB = Annotated[Session, Depends(get_db)]
Cache = Annotated[FlagConfigCache, Depends(get_cache)]
KeyCache = Annotated[ApiKeyCache, Depends(get_key_cache)]


# ----- flags -----
@router.get("/flags", response_model=FlagListOut)
def list_flags(
    admin: Admin,
    db: DB,
    cache: Cache,
    include_archived: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> FlagListOut:
    flags = FlagService(db, cache, admin.actor).list(include_archived=include_archived, search=search)
    return FlagListOut(items=[to_flag_out(f) for f in flags], total=len(flags))


@router.post("/flags", response_model=FlagOut, status_code=201, responses={409: {"model": ErrorResponse}})
def create_flag(body: FlagCreate, admin: Admin, db: DB, cache: Cache) -> FlagOut:
    return to_flag_out(FlagService(db, cache, admin.actor).create(body))


@router.get("/flags/{key}", response_model=FlagOut)
def get_flag(key: FlagKey, admin: Admin, db: DB, cache: Cache) -> FlagOut:
    return to_flag_out(FlagService(db, cache, admin.actor).get(key))


@router.patch("/flags/{key}", response_model=FlagOut)
def update_flag(key: FlagKey, body: FlagUpdate, admin: Admin, db: DB, cache: Cache) -> FlagOut:
    """Edit name/description. The key is immutable because it feeds the rollout bucketing hash."""
    return to_flag_out(FlagService(db, cache, admin.actor).update_metadata(key, body))


@router.patch(
    "/flags/{key}/environments/{environment}",
    response_model=FlagOut,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def update_flag_config(
    key: FlagKey, environment: EnvironmentKey, body: ConfigUpdate, admin: Admin, db: DB, cache: Cache
) -> FlagOut:
    """Partially update one environment's configuration. Other environments are never touched."""
    return to_flag_out(FlagService(db, cache, admin.actor).update_config(key, environment, body))


@router.post("/flags/{key}/archive", response_model=FlagOut, responses={409: {"model": ErrorResponse}})
def archive_flag(key: FlagKey, admin: Admin, db: DB, cache: Cache) -> FlagOut:
    return to_flag_out(FlagService(db, cache, admin.actor).archive(key))


@router.post("/flags/{key}/restore", response_model=FlagOut, responses={409: {"model": ErrorResponse}})
def restore_flag(key: FlagKey, admin: Admin, db: DB, cache: Cache) -> FlagOut:
    return to_flag_out(FlagService(db, cache, admin.actor).restore(key))


# ----- playground -----
@router.post("/evaluate", response_model=AdminEvaluateResponse)
def playground_evaluate(body: AdminEvaluateRequest, db: DB, cache: Cache) -> AdminEvaluateResponse:
    """Evaluate through the exact same service (cache included) as the public API, for any environment."""
    outcome = EvaluationService(db, cache).evaluate(body.environment, body.flag_key, body.user_id)
    return AdminEvaluateResponse(
        flag_key=outcome.flag_key,
        enabled=outcome.result.enabled,
        reason=outcome.result.reason,
        environment=body.environment,
        bucket=outcome.result.bucket,
        rollout_percentage=outcome.rollout_percentage,
        source=outcome.source,
    )


# ----- audit + stats -----
@router.get("/audit", response_model=AuditListOut)
def list_audit(
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    flag_key: Annotated[str | None, Query(max_length=64)] = None,
) -> AuditListOut:
    items, total = AuditRepository(db).list(limit=limit, offset=offset, flag_key=flag_key)
    return AuditListOut(items=[AuditEventOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=StatsOut)
def stats(db: DB) -> StatsOut:
    return build_stats(db)


# ----- API keys -----
@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(admin: Admin, db: DB, key_cache: KeyCache) -> list[ApiKeyOut]:
    return [ApiKeyOut.model_validate(k) for k in ApiKeyService(db, key_cache, admin.actor).list()]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(body: ApiKeyCreate, admin: Admin, db: DB, key_cache: KeyCache) -> ApiKeyCreated:
    """Create an environment-scoped evaluation key. The secret is returned only in this response."""
    key, secret = ApiKeyService(db, key_cache, admin.actor).create(body)
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=secret)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyOut, responses={409: {"model": ErrorResponse}})
def revoke_api_key(key_id: uuid.UUID, admin: Admin, db: DB, key_cache: KeyCache) -> ApiKeyOut:
    return ApiKeyOut.model_validate(ApiKeyService(db, key_cache, admin.actor).revoke(key_id))
