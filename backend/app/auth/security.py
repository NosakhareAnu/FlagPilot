"""Password hashing and token helpers."""

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library-default (RFC 9106 low-memory) parameters
# Verified against when the e-mail is unknown so login timing does not reveal which e-mails exist.
_DUMMY_HASH = _hasher.hash("flagpilot-dummy-password")

API_KEY_RE = re.compile(r"^fpk_(development|production)_[A-Za-z0-9_-]{32,128}$")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def generate_api_key(environment: str) -> str:
    return f"fpk_{environment}_{secrets.token_urlsafe(32)}"


def api_key_display_prefix(key: str, environment: str) -> str:
    return key[: len(f"fpk_{environment}_") + 6]
