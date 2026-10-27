from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
# Non-secret hint for the Next.js route guard, which can't see the path-scoped refresh
# cookie. It only decides whether to show the login page; the API still checks tokens.
SESSION_HINT_COOKIE = "jp_session"
CSRF_HEADER = "x-csrf-token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

_JWT_ALG = "HS256"


@lru_cache
def _hasher() -> PasswordHasher:
    # argon2id defaults (64 MiB); tests lower the memory cost to stay fast and light.
    return PasswordHasher(memory_cost=get_settings().password_hash_memory_kib)


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher().verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher().check_needs_rehash(password_hash)


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALG)


def decode_access_token(token: str) -> AccessClaims | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    try:
        return AccessClaims(user_id=UUID(payload["sub"]), session_id=UUID(payload["sid"]))
    except (KeyError, ValueError):
        return None


def sign_state(data: dict[str, Any], ttl_seconds: int = 600) -> str:
    """Short-lived signed blob, used for the OAuth state/PKCE cookie."""
    payload = {**data, "typ": "state", "exp": datetime.now(UTC) + timedelta(seconds=ttl_seconds)}
    return jwt.encode(payload, get_settings().secret_key, algorithm=_JWT_ALG)


def read_state(token: str) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, get_settings().secret_key, algorithms=[_JWT_ALG]
        )
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "state" else None
