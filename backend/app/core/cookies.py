from __future__ import annotations

from fastapi import Response

from app.core import security
from app.core.config import get_settings
from app.services.auth_service import SessionTokens


def set_session_cookies(response: Response, tokens: SessionTokens) -> None:
    settings = get_settings()
    secure = settings.cookie_secure
    response.set_cookie(
        security.ACCESS_COOKIE,
        tokens.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        security.REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=security.REFRESH_COOKIE_PATH,
    )
    # Readable by JS on purpose: the frontend echoes it in the X-CSRF-Token header.
    response.set_cookie(
        security.CSRF_COOKIE,
        tokens.csrf_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        security.SESSION_HINT_COOKIE,
        "1",
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(security.ACCESS_COOKIE, path="/")
    response.delete_cookie(security.REFRESH_COOKIE, path=security.REFRESH_COOKIE_PATH)
    response.delete_cookie(security.CSRF_COOKIE, path="/")
    response.delete_cookie(security.SESSION_HINT_COOKIE, path="/")
