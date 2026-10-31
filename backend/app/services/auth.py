from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.security import new_token, sha256_hex, verify_password
from app.models import AdminSession, AdminUser
from app.repositories.auth import AdminRepository


@dataclass(frozen=True, slots=True)
class LoginResult:
    token: str  # raw cookie value; only its hash is stored
    csrf_token: str
    user: AdminUser
    expires_at: datetime


class AuthService:
    def __init__(self, db: Session, session_ttl_hours: int) -> None:
        self.db = db
        self.repo = AdminRepository(db)
        self.ttl = timedelta(hours=session_ttl_hours)

    def login(self, email: str, password: str) -> LoginResult | None:
        user = self.repo.get_user_by_email(email.strip().lower())
        # verify_password burns equal time for unknown e-mails (dummy hash) so timing doesn't enumerate accounts
        if not verify_password(user.password_hash if user else None, password) or user is None:
            return None
        token, csrf = new_token(), new_token()
        expires = datetime.now(UTC) + self.ttl
        self.repo.purge_expired_sessions()
        self.repo.add_session(AdminSession(token_hash=sha256_hex(token), user_id=user.id, csrf_token=csrf, expires_at=expires))
        self.db.commit()
        return LoginResult(token, csrf, user, expires)

    def resolve(self, token: str) -> tuple[AdminSession, AdminUser] | None:
        session = self.repo.get_session(sha256_hex(token))
        if session is None:
            return None
        user = self.repo.get_user(session.user_id)
        return (session, user) if user else None

    def logout(self, token: str) -> None:
        self.repo.delete_session(sha256_hex(token))
        self.db.commit()
