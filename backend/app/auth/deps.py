"""Request-scoped dependencies: client IP, rate limiting, admin session + CSRF, API-key authentication."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth.security import API_KEY_RE, constant_time_equals, sha256_hex
from app.cache import ApiKeyCache, FlagConfigCache, RateLimiter
from app.config import Settings, get_settings
from app.db import get_db
from app.models import AdminUser
from app.repositories.auth import ApiKeyRepository
from app.services.auth import AuthService
from app.services.errors import DomainError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
AUTH_FAILURE_LIMIT_PER_WINDOW = 30


class Unauthorized(DomainError):
    status_code = 401
    code = "unauthorized"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class TooManyRequests(DomainError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# ----- app-state accessors (swappable in tests) -----
def get_cache(request: Request) -> FlagConfigCache:
    return request.app.state.flag_cache


def get_key_cache(request: Request) -> ApiKeyCache:
    return request.app.state.key_cache


def get_limiter(request: Request) -> RateLimiter:
    return request.app.state.limiter


def client_ip(request: Request, settings: Settings) -> str:
    """Client address for rate limiting. X-Forwarded-For is only honoured for the configured number of trusted proxy
    hops, and only the entry appended by the trusted proxy is used (never the client-supplied left-hand entries)."""
    peer = request.client.host if request.client else "unknown"
    hops = settings.trusted_proxy_hops
    if hops > 0:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
        if len(entries) >= hops:
            return entries[-hops][:64]
    return peer


def enforce(limiter: RateLimiter, scope: str, ident: str, limit: int, response: Response | None = None) -> None:
    result = limiter.hit(scope, ident, limit)
    if response is not None:
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_seconds)
    if not result.allowed:
        raise TooManyRequests("Rate limit exceeded. Retry later.", result.reset_seconds)


def check_origin(request: Request, settings: Settings) -> None:
    """Browsers always send Origin on cross-site and same-site unsafe requests; require it to be one of ours."""
    origin = request.headers.get("origin")
    if origin is None or origin.rstrip("/") not in settings.allowed_origins:
        raise Forbidden("Origin not allowed")


# ----- admin (dashboard) auth -----
@dataclass(frozen=True, slots=True)
class AdminContext:
    user: AdminUser
    csrf_token: str
    token: str

    @property
    def actor(self) -> str:
        return self.user.email


def require_admin(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_limiter),
) -> AdminContext:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise Unauthorized("Authentication required")
    resolved = AuthService(db, settings.session_ttl_hours).resolve(token)
    if resolved is None:
        raise Unauthorized("Session expired or invalid")
    session, user = resolved
    if request.method not in SAFE_METHODS:
        check_origin(request, settings)
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not constant_time_equals(supplied, session.csrf_token):
            raise Forbidden("Missing or invalid CSRF token")
    enforce(limiter, "admin", sha256_hex(token)[:16], settings.admin_rate_limit, response)
    return AdminContext(user=user, csrf_token=session.csrf_token, token=token)


# ----- evaluation API-key auth -----
@dataclass(frozen=True, slots=True)
class ApiKeyContext:
    key_id: str
    environment: str


def _throttle_failures(limiter: RateLimiter, ip: str) -> None:
    if limiter.count("apikey-fail", ip) >= AUTH_FAILURE_LIMIT_PER_WINDOW:
        raise TooManyRequests("Too many failed authentication attempts.", 60)


def require_api_key(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_limiter),
    key_cache: ApiKeyCache = Depends(get_key_cache),
) -> ApiKeyContext:
    ip = client_ip(request, settings)
    header = request.headers.get("authorization", "")
    scheme, _, secret = header.partition(" ")
    secret = secret.strip()
    if scheme.lower() != "bearer" or not API_KEY_RE.match(secret):
        _throttle_failures(limiter, ip)
        limiter.hit("apikey-fail", ip, AUTH_FAILURE_LIMIT_PER_WINDOW)
        raise Unauthorized("Missing or malformed API key. Send 'Authorization: Bearer <key>'.")
    key_hash = sha256_hex(secret)
    cached = key_cache.get(key_hash)
    if cached is not None:  # known-good key: hot path, no failure-counter round trip
        key_id, environment = cached["id"], cached["environment"]
    else:
        # Cache miss means a database lookup: first refuse clients that keep presenting bad credentials.
        _throttle_failures(limiter, ip)
        record = ApiKeyRepository(db).get_active_by_hash(key_hash)
        if record is None:
            limiter.hit("apikey-fail", ip, AUTH_FAILURE_LIMIT_PER_WINDOW)
            raise Unauthorized("Invalid or revoked API key")
        key_id, environment = str(record.id), record.environment
        key_cache.set(key_hash, key_id, environment)
    enforce(limiter, "eval", key_id, settings.eval_rate_limit, response)
    return ApiKeyContext(key_id=key_id, environment=environment)
