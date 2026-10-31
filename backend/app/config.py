"""Application settings, loaded from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "INFO"

    # No credentials in source: the real URL (with the generated password) always comes from DATABASE_URL.
    database_url: str = "postgresql+psycopg://flagpilot@localhost:5432/flagpilot"
    redis_url: str = "redis://localhost:6379/0"
    redis_socket_timeout: float = 0.25  # seconds; keep short so a dead Redis never stalls requests
    redis_retry_cooldown: float = 5.0  # seconds to skip Redis after a failure (circuit breaker)

    # Flag-config cache
    cache_ttl_seconds: int = 30
    negative_cache_ttl_seconds: int = 10

    # Dashboard auth
    admin_email: str = "admin@flagpilot.local"
    admin_password: SecretStr = SecretStr("")
    session_ttl_hours: int = 12
    session_cookie_name: str = "fp_session"
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"

    # Rate limiting (requests per window)
    rate_limit_window_seconds: int = 60
    eval_rate_limit: int = 600
    admin_rate_limit: int = 300
    login_rate_limit: int = 10

    # Bootstrap (idempotent on startup)
    seed_demo_data: bool = False
    bootstrap_api_key_development: SecretStr = SecretStr("")
    bootstrap_api_key_production: SecretStr = SecretStr("")

    # Number of trusted reverse proxies in front of the API (0 = ignore X-Forwarded-For entirely).
    # With N hops the client IP is the N-th entry from the RIGHT, i.e. the address the outermost trusted proxy saw;
    # entries to its left are client-controlled and therefore spoofable.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
