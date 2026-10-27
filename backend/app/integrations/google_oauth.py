"""Google OAuth 2.0 (authorization code + PKCE) over plain httpx."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (endpoint, not a secret)
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
LOGIN_SCOPES = ("openid", "email", "profile")

_transient = retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError))


class GoogleOAuthError(Exception):
    pass


@dataclass(frozen=True)
class PkcePair:
    verifier: str
    challenge: str


@dataclass(frozen=True)
class GoogleUserInfo:
    subject: str
    email: str
    email_verified: bool
    name: str | None


def new_pkce() -> PkcePair:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return PkcePair(verifier=verifier, challenge=challenge)


def authorization_url(
    *, redirect_uri: str, state: str, code_challenge: str, scopes: tuple[str, ...] = LOGIN_SCOPES
) -> str:
    params = {
        "client_id": get_settings().google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


@retry(retry=_transient, stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 8))
async def _post_token(data: dict[str, str]) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(TOKEN_URL, data=data)
    if resp.status_code >= 500:
        resp.raise_for_status()
    if resp.status_code != 200:
        raise GoogleOAuthError(f"token exchange failed ({resp.status_code})")
    payload: dict[str, object] = resp.json()
    return payload


async def exchange_code(*, code: str, redirect_uri: str, code_verifier: str) -> dict[str, object]:
    settings = get_settings()
    return await _post_token(
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
    )


@retry(retry=_transient, stop=stop_after_attempt(3), wait=wait_exponential_jitter(1, 8))
async def fetch_userinfo(access_token: str) -> GoogleUserInfo:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code >= 500:
        resp.raise_for_status()
    if resp.status_code != 200:
        raise GoogleOAuthError(f"userinfo failed ({resp.status_code})")
    data = resp.json()
    return GoogleUserInfo(
        subject=str(data["sub"]),
        email=str(data["email"]),
        email_verified=bool(data.get("email_verified")),
        name=data.get("name"),
    )
