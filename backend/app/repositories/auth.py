from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AdminSession, AdminUser, ApiKey


class AdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> AdminUser | None:
        return self.db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()

    def get_user(self, user_id) -> AdminUser | None:
        return self.db.get(AdminUser, user_id)

    def add_session(self, session: AdminSession) -> None:
        self.db.add(session)

    def get_session(self, token_hash: str) -> AdminSession | None:
        return self.db.execute(
            select(AdminSession).where(AdminSession.token_hash == token_hash, AdminSession.expires_at > datetime.now(UTC))
        ).scalar_one_or_none()

    def delete_session(self, token_hash: str) -> None:
        self.db.execute(delete(AdminSession).where(AdminSession.token_hash == token_hash))

    def purge_expired_sessions(self) -> None:
        self.db.execute(delete(AdminSession).where(AdminSession.expires_at <= datetime.now(UTC)))


class ApiKeyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        return self.db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        ).scalar_one_or_none()

    def get_by_hash(self, key_hash: str) -> ApiKey | None:
        return self.db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash)).scalar_one_or_none()

    def get(self, key_id) -> ApiKey | None:
        return self.db.get(ApiKey, key_id)

    def list(self) -> list[ApiKey]:
        return list(self.db.execute(select(ApiKey).order_by(ApiKey.created_at.desc())).scalars())

    def add(self, key: ApiKey) -> None:
        self.db.add(key)
        self.db.flush()
