from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import google_oauth
from app.models import AuditLog, OAuthAccount, RefreshToken, User
from tests.conftest import FakeMailer, csrf_headers, login, signup_and_verify

PASSWORD = "correct horse battery"


async def test_signup_verify_login_me(client: AsyncClient, mailer: FakeMailer) -> None:
    await signup_and_verify(client, mailer)
    await login(client)

    assert client.cookies.get("access_token")
    assert client.cookies.get("csrf_token")
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "ada@example.com"
    assert body["email_verified"] is True
    assert body["onboarding_step"] == "resume"
    assert body["daily_send_cap"] == 25


async def test_signup_does_not_reveal_existing_accounts(
    client: AsyncClient, mailer: FakeMailer
) -> None:
    await signup_and_verify(client, mailer)
    sent_before = len(mailer.sent)
    r = await client.post(
        "/api/v1/auth/signup", json={"email": "ada@example.com", "password": PASSWORD}
    )
    assert r.status_code == 202
    assert len(mailer.sent) == sent_before  # verified account: nothing to resend


async def test_login_requires_verified_email(client: AsyncClient, mailer: FakeMailer) -> None:
    await client.post("/api/v1/auth/signup", json={"email": "bo@example.com", "password": PASSWORD})
    r = await client.post(
        "/api/v1/auth/login", json={"email": "bo@example.com", "password": PASSWORD}
    )
    assert r.status_code == 403
    assert r.json()["code"] == "email_not_verified"


async def test_wrong_password_and_unknown_email(client: AsyncClient, mailer: FakeMailer) -> None:
    await signup_and_verify(client, mailer)
    for email, pw in [("ada@example.com", "nope-nope-nope"), ("ghost@example.com", PASSWORD)]:
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 401
        assert r.json()["code"] == "invalid_credentials"


async def test_weak_password_rejected(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/signup", json={"email": "c@example.com", "password": "short"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


async def test_verification_token_single_use(client: AsyncClient, mailer: FakeMailer) -> None:
    await client.post("/api/v1/auth/signup", json={"email": "d@example.com", "password": PASSWORD})
    token = mailer.last_token()
    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": token})
    ).status_code == 200
    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_token"


async def test_me_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_refresh_rotation_and_reuse_detection(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    await signup_and_verify(client, mailer)
    await login(client)
    first_refresh = client.cookies.get("refresh_token", path="/api/v1/auth")
    assert first_refresh

    r = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert r.status_code == 200
    second_refresh = client.cookies.get("refresh_token", path="/api/v1/auth")
    assert second_refresh and second_refresh != first_refresh

    # Replaying the rotated-out token revokes the whole family.
    client.cookies.set("refresh_token", first_refresh, path="/api/v1/auth")
    r = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert r.status_code == 401

    active = await db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
    assert list(active) == []
    actions = list(await db.scalars(select(AuditLog.action)))
    assert "refresh_token_reuse" in actions


async def test_csrf_required_for_cookie_requests(client: AsyncClient, mailer: FakeMailer) -> None:
    await signup_and_verify(client, mailer)
    await login(client)
    r = await client.patch("/api/v1/users/me", json={"full_name": "Ada"})
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"

    r = await client.patch(
        "/api/v1/users/me", json={"full_name": "Ada"}, headers=csrf_headers(client)
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Ada"


async def test_update_me_validation(client: AsyncClient, mailer: FakeMailer) -> None:
    await signup_and_verify(client, mailer)
    await login(client)
    h = csrf_headers(client)
    r = await client.patch("/api/v1/users/me", json={"daily_send_cap": 500}, headers=h)
    assert r.status_code == 422
    assert r.json()["code"] == "send_cap_too_high"
    r = await client.patch("/api/v1/users/me", json={"timezone": "Mars/Base"}, headers=h)
    assert r.status_code == 422
    r = await client.patch(
        "/api/v1/users/me", json={"timezone": "Asia/Karachi", "daily_send_cap": 10}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["timezone"] == "Asia/Karachi"


async def test_logout_revokes_session(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    await signup_and_verify(client, mailer)
    await login(client)
    r = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert r.status_code == 200
    assert client.cookies.get("access_token") is None
    active = await db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
    assert list(active) == []


async def test_password_reset_flow(client: AsyncClient, mailer: FakeMailer) -> None:
    await signup_and_verify(client, mailer)
    r = await client.post("/api/v1/auth/password/forgot", json={"email": "ada@example.com"})
    assert r.status_code == 202
    assert "/reset-password?token=" in mailer.last_link()

    new_pw = "a brand new passphrase"
    r = await client.post(
        "/api/v1/auth/password/reset", json={"token": mailer.last_token(), "password": new_pw}
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD}
    )
    assert r.status_code == 401
    await login(client, password=new_pw)

    # Unknown emails get the same response and no mail.
    sent = len(mailer.sent)
    r = await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "ghost@example.com"},
        headers=csrf_headers(client),
    )
    assert r.status_code == 202
    assert len(mailer.sent) == sent


async def test_google_start_sets_state_and_pkce(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/google/start")
    assert r.status_code == 302
    query = parse_qs(urlparse(r.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://localhost:3000/api/v1/auth/google/callback"]
    assert client.cookies.get("g_oauth_state", path="/api/v1/auth/google")


async def test_google_callback_rejects_bad_state(client: AsyncClient) -> None:
    await client.get("/api/v1/auth/google/start")
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": "wrong"})
    assert r.status_code == 302
    assert r.headers["location"].endswith("/login?error=google_state")
    assert client.cookies.get("access_token") is None


@respx.mock
async def test_google_login_creates_and_links_user(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    # Existing unverified password account with the same email gets linked + verified.
    await client.post(
        "/api/v1/auth/signup", json={"email": "gina@example.com", "password": PASSWORD}
    )

    respx.post(google_oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "g-access", "expires_in": 3600})
    )
    respx.get(google_oauth.USERINFO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "sub": "g-123",
                "email": "gina@example.com",
                "email_verified": True,
                "name": "Gina",
            },
        )
    )

    start = await client.get("/api/v1/auth/google/start")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": state})
    assert r.status_code == 302
    assert r.headers["location"] == "http://localhost:3000/onboarding"
    assert client.cookies.get("access_token")

    me = (await client.get("/api/v1/users/me")).json()
    assert me["email"] == "gina@example.com" and me["email_verified"] is True

    users = list(await db.scalars(select(User)))
    accounts = list(await db.scalars(select(OAuthAccount)))
    assert len(users) == 1
    assert len(accounts) == 1 and accounts[0].provider_subject == "g-123"


@respx.mock
async def test_google_login_rejects_unverified_google_email(client: AsyncClient) -> None:
    respx.post(google_oauth.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "g-access"})
    )
    respx.get(google_oauth.USERINFO_URL).mock(
        return_value=httpx.Response(
            200, json={"sub": "g-9", "email": "x@example.com", "email_verified": False}
        )
    )
    start = await client.get("/api/v1/auth/google/start")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": state})
    assert r.headers["location"].endswith("/login?error=google_failed")
