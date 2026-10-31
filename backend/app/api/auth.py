from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth.deps import (
    AdminContext,
    Unauthorized,
    check_origin,
    client_ip,
    enforce,
    get_limiter,
    require_admin,
)
from app.cache import RateLimiter
from app.config import Settings, get_settings
from app.db import get_db
from app.schemas.auth import LoginRequest, SessionOut
from app.schemas.common import ErrorResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=SessionOut, responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: RateLimiter = Depends(get_limiter),
) -> SessionOut:
    """Start an administrator session (HttpOnly cookie). Brute force is throttled per client IP."""
    check_origin(request, settings)
    enforce(limiter, "login", client_ip(request, settings), settings.login_rate_limit)
    result = AuthService(db, settings.session_ttl_hours).login(body.email, body.password)
    if result is None:
        raise Unauthorized("Invalid email or password")
    response.set_cookie(
        settings.session_cookie_name,
        result.token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionOut(email=result.user.email, csrf_token=result.csrf_token)


@router.get("/me", response_model=SessionOut, responses={401: {"model": ErrorResponse}})
def me(ctx: AdminContext = Depends(require_admin)) -> SessionOut:
    """Current session; the frontend reads the CSRF token from here."""
    return SessionOut(email=ctx.user.email, csrf_token=ctx.csrf_token)


@router.post("/logout", status_code=204, responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
def logout(
    response: Response,
    ctx: AdminContext = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    AuthService(db, settings.session_ttl_hours).logout(ctx.token)
    out = Response(status_code=204)
    out.delete_cookie(settings.session_cookie_name, path="/")
    return out
