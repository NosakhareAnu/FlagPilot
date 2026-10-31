"""FastAPI application factory."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, auth, evaluate, health
from app.auth.deps import TooManyRequests
from app.cache import ApiKeyCache, FlagConfigCache, RateLimiter, RedisGuard
from app.config import Settings, get_settings
from app.db import get_engine
from app.logging_config import configure_logging
from app.services.bootstrap import run_bootstrap
from app.services.errors import DomainError

log = logging.getLogger("flagpilot")

DESCRIPTION = """
Self-hosted feature flag platform.

* **Evaluation API** (`POST /api/v1/evaluate`) is authenticated with an environment-scoped API key (`Authorization: Bearer fpk_...`).
* **Admin API** (`/api/v1/admin/*`) is used by the dashboard and authenticated by an HttpOnly session cookie plus `X-CSRF-Token`.

Evaluation precedence: kill switch / disabled -> excluded user -> included user -> percentage rollout -> default disabled.
"""


def error_response(status: int, code: str, message: str, request: Request, details: list[dict] | None = None, headers: dict | None = None):
    body = {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status, headers=headers)


def create_app(settings: Settings | None = None, redis_client: redis.Redis | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            with app.state.session_factory() as db:
                run_bootstrap(db, settings, app.state.flag_cache)
        except Exception:  # DB not ready yet: the app starts, /health/ready reports it, Compose retries migrations
            log.exception("bootstrap failed; continuing so health endpoints can report the problem")
        yield

    app = FastAPI(title="FlagPilot API", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)

    # ---- shared infrastructure on app.state (swappable in tests) ----
    client = redis_client or redis.Redis.from_url(
        settings.redis_url,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_timeout,
        decode_responses=True,
    )
    guard = RedisGuard(client, cooldown=settings.redis_retry_cooldown)
    app.state.redis_guard = guard
    app.state.flag_cache = FlagConfigCache(guard, settings.cache_ttl_seconds, settings.negative_cache_ttl_seconds)
    app.state.key_cache = ApiKeyCache(guard)
    app.state.limiter = RateLimiter(guard, settings.rate_limit_window_seconds)
    app.state.session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)

    # ---- middleware (last added = outermost) ----
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/") or request.url.path.startswith("/health"):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path != "/health/live":
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,  # path only: no query string, no headers, no bodies
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    "request_id": request_id,
                },
            )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "X-FlagPilot-Cache", "Retry-After"],
    )

    # ---- exception handlers: stable { "error": {code, message} } shape, never stack traces ----
    @app.exception_handler(TooManyRequests)
    async def _rate_limited(request: Request, exc: TooManyRequests):
        return error_response(429, exc.code, exc.message, request, headers={"Retry-After": str(exc.retry_after)})

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError):
        return error_response(exc.status_code, exc.code, exc.message, request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Strip 'input' / 'ctx' so submitted values (possibly secrets) are never echoed back.
        details = [{"loc": [str(p) for p in e["loc"]], "message": e["msg"], "type": e["type"]} for e in exc.errors()]
        return error_response(422, "validation_error", "Request validation failed", request, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail), request)

    @app.exception_handler(OperationalError)
    async def _db_down(request: Request, exc: OperationalError):
        log.error("database unavailable", extra={"request_id": request.state.request_id})
        return error_response(503, "database_unavailable", "The service is temporarily unavailable. Try again shortly.", request, headers={"Retry-After": "5"})

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(request: Request, exc: SQLAlchemyError):
        log.error("database error", extra={"request_id": request.state.request_id, "error": type(exc).__name__})
        status = 503 if isinstance(exc, DBAPIError) and exc.connection_invalidated else 500
        return error_response(status, "database_error", "An internal error occurred.", request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error", extra={"request_id": getattr(request.state, "request_id", None)})
        return error_response(500, "internal_error", "An internal error occurred.", request)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(evaluate.router)
    return app


def build_default_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    return create_app()
