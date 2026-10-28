"""Gmail: connect (OAuth, offline access), refresh tokens, send one message, disconnect.

By default only the gmail.send scope is requested: the app can send as the user but can't
read mail. Reply detection asks for read-only access separately (connect with read=true).
send_raw is called only by send_service.deliver (the queued, user-confirmed send).
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations import google_oauth

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
# Optional, for reply detection: read-only, and the app only searches for messages from the
# contacts and companies you applied to.
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = ("openid", "email", SEND_SCOPE)
MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailAuthError(Exception):
    """The user must reconnect Gmail (revoked, expired testing-mode token, missing scope)."""


class GmailSendError(Exception):
    """Gmail refused or failed to send; `retryable` when trying later may work."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scopes: list[str]


@dataclass(frozen=True)
class Sent:
    message_id: str
    thread_id: str | None


def consent_url(
    state: str, code_challenge: str, login_hint: str | None = None, *, read: bool = False
) -> str:
    extra = {
        "access_type": "offline",  # a refresh token, so sends work when the user is away
        "prompt": "consent",  # always return a refresh token, even on reconnect
        "include_granted_scopes": "true",
    }
    if login_hint:
        extra["login_hint"] = login_hint
    return google_oauth.authorization_url(
        redirect_uri=get_settings().google_gmail_redirect_uri,
        state=state,
        code_challenge=code_challenge,
        scopes=(*SCOPES, READ_SCOPE) if read else SCOPES,
        extra=extra,
    )


def parse_tokens(payload: dict[str, Any], refresh_token: str | None = None) -> Tokens:
    return Tokens(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload.get("refresh_token") or refresh_token or "") or None,
        expires_at=datetime.now(UTC) + timedelta(seconds=int(payload.get("expires_in", 3600))),
        scopes=str(payload.get("scope", "")).split(),
    )


async def exchange(code: str, code_verifier: str) -> Tokens:
    payload = await google_oauth.exchange_code(
        code=code,
        redirect_uri=get_settings().google_gmail_redirect_uri,
        code_verifier=code_verifier,
    )
    tokens = parse_tokens(payload)
    if SEND_SCOPE not in tokens.scopes:
        raise GmailAuthError("Permission to send email wasn't granted.")
    return tokens


def refresh(refresh_token: str) -> Tokens:
    settings = get_settings()
    try:
        resp = httpx.post(
            google_oauth.TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
    except httpx.TransportError as exc:
        raise GmailSendError("Couldn't reach Google.", retryable=True) from exc
    if resp.status_code in (400, 401):  # invalid_grant: revoked or expired (7 days in Testing)
        raise GmailAuthError("Gmail access expired or was revoked. Reconnect Gmail.")
    if resp.status_code != 200:
        raise GmailSendError(f"Google token refresh failed ({resp.status_code}).", retryable=True)
    return parse_tokens(resp.json(), refresh_token)


def send_raw(access_token: str, mime: bytes) -> Sent:
    raw = base64.urlsafe_b64encode(mime).decode()
    try:
        resp = httpx.post(
            SEND_URL,
            json={"raw": raw},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except httpx.TransportError as exc:
        raise GmailSendError("Couldn't reach Gmail.", retryable=True) from exc
    if resp.status_code == 401:
        raise GmailAuthError("Gmail access token was rejected.")
    if resp.status_code == 403:
        raise GmailAuthError("Gmail permission is missing. Reconnect Gmail.")
    if resp.status_code == 429 or resp.status_code >= 500:
        raise GmailSendError(f"Gmail is busy ({resp.status_code}).", retryable=True)
    if resp.status_code != 200:
        raise GmailSendError(f"Gmail refused the message ({resp.status_code}).", retryable=False)
    data = resp.json()
    return Sent(message_id=str(data["id"]), thread_id=data.get("threadId"))


async def revoke(token: str) -> None:
    """Best effort: the tokens are deleted on our side either way."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(google_oauth.REVOKE_URL, data={"token": token})
    except httpx.HTTPError:
        pass


@dataclass(frozen=True)
class MessageMeta:
    id: str
    thread_id: str | None
    sender: str  # the From address, lowercased
    subject: str
    snippet: str  # Gmail's short preview, not the full body
    received_at: datetime


def _get(token: str, url: str, params: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except httpx.TransportError as exc:
        raise GmailSendError("Couldn't reach Gmail.", retryable=True) from exc
    if resp.status_code == 401:
        raise GmailAuthError("Gmail access token was rejected.")
    if resp.status_code == 403:
        raise GmailAuthError("Reading Gmail isn't allowed. Turn on reply detection again.")
    if resp.status_code != 200:
        raise GmailSendError(
            f"Gmail failed ({resp.status_code}).", retryable=resp.status_code >= 429
        )
    data: dict[str, Any] = resp.json()
    return data


def search(token: str, query: str, limit: int = 50) -> list[str]:
    """Message ids matching a Gmail search (e.g. "from:(a@x.com OR y.com) after:1700000000")."""
    data = _get(token, MESSAGES_URL, (("q", query), ("maxResults", str(limit))))
    return [str(m["id"]) for m in data.get("messages") or []]


def message_meta(token: str, message_id: str) -> MessageMeta:
    """Headers and Gmail's snippet only: the full message body is never downloaded."""
    data = _get(
        token,
        f"{MESSAGES_URL}/{message_id}",
        (("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Subject")),
    )
    headers = {
        h["name"].lower(): h["value"] for h in (data.get("payload") or {}).get("headers", [])
    }
    return MessageMeta(
        id=str(data["id"]),
        thread_id=data.get("threadId"),
        sender=parseaddr(headers.get("from", ""))[1].lower(),
        subject=headers.get("subject", "")[:300],
        snippet=html.unescape(str(data.get("snippet") or ""))[:500],
        received_at=datetime.fromtimestamp(int(data.get("internalDate", 0)) / 1000, UTC),
    )
