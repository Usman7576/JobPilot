from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.core import security
from app.core.config import get_settings
from app.core.cookies import clear_session_cookies, set_session_cookies
from app.core.deps import Client, DbSession, MailerDep
from app.core.errors import AppError, Unauthorized, problem
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.integrations import google_oauth
from app.models.enums import OnboardingStep
from app.schemas.auth import (
    AuthConfigOut,
    ForgotPasswordIn,
    LoginIn,
    ResendVerificationIn,
    ResetPasswordIn,
    SignupIn,
    UserOut,
    VerifyEmailIn,
)
from app.schemas.common import MessageOut
from app.services import auth_service
from app.services.user_service import to_user_out

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)

GOOGLE_STATE_COOKIE = "g_oauth_state"
GOOGLE_STATE_PATH = "/api/v1/auth/google"
CHECK_INBOX = "If that address can sign up, we've sent a verification link. Check your inbox."


@router.get("/config")
async def get_config() -> AuthConfigOut:
    settings = get_settings()
    return AuthConfigOut(
        google_login_enabled=settings.google_login_enabled,
        require_email_verification=settings.require_email_verification,
    )


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
async def signup(request: Request, body: SignupIn, db: DbSession, mailer: MailerDep) -> MessageOut:
    await auth_service.signup(
        db, mailer, email=body.email, password=body.password, full_name=body.full_name
    )
    return MessageOut(message=CHECK_INBOX)


@router.post("/verify-email")
@limiter.limit("20/hour")
async def verify_email(request: Request, body: VerifyEmailIn, db: DbSession) -> MessageOut:
    await auth_service.verify_email(db, body.token)
    return MessageOut(message="Email verified. You can sign in now.")


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
async def resend_verification(
    request: Request, body: ResendVerificationIn, db: DbSession, mailer: MailerDep
) -> MessageOut:
    await auth_service.resend_verification(db, mailer, body.email)
    return MessageOut(message=CHECK_INBOX)


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request, response: Response, body: LoginIn, db: DbSession, client: Client
) -> UserOut:
    user = await auth_service.authenticate(db, email=body.email, password=body.password)
    tokens = await auth_service.start_session(db, user, client)
    set_session_cookies(response, tokens)
    return to_user_out(user)


@router.post("/refresh", response_model=MessageOut)
@limiter.limit("60/minute")
async def refresh(
    request: Request, response: Response, db: DbSession, client: Client
) -> MessageOut | JSONResponse:
    token = request.cookies.get(security.REFRESH_COOKIE)
    try:
        if not token:
            raise Unauthorized()
        tokens = await auth_service.rotate_refresh(db, token, client)
    except Unauthorized as exc:
        # The session is over: answer 401 *and* drop the cookies, including the
        # "signed in" hint, or the homepage would keep forwarding to the app and on to login.
        # (Cookies set on `response` are lost when an exception is raised, so build it here.)
        failed = problem(exc.status_code, exc.code, exc.title, exc.detail)
        clear_session_cookies(failed)
        return failed
    set_session_cookies(response, tokens)
    return MessageOut(message="refreshed")


@router.post("/logout")
async def logout(request: Request, response: Response, db: DbSession) -> MessageOut:
    await auth_service.logout(db, request.cookies.get(security.REFRESH_COOKIE))
    clear_session_cookies(response)
    return MessageOut(message="Signed out")


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour")
async def forgot_password(
    request: Request, body: ForgotPasswordIn, db: DbSession, mailer: MailerDep
) -> MessageOut:
    await auth_service.forgot_password(db, mailer, body.email)
    return MessageOut(message="If an account exists for that email, a reset link is on its way.")


@router.post("/password/reset")
@limiter.limit("10/hour")
async def reset_password(request: Request, body: ResetPasswordIn, db: DbSession) -> MessageOut:
    await auth_service.reset_password(db, token=body.token, password=body.password)
    return MessageOut(message="Password updated. Please sign in.")


# --- Google login ---------------------------------------------------------------------


@router.get("/google/start", response_class=RedirectResponse, status_code=302)
@limiter.limit("20/minute")
async def google_start(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not settings.google_login_enabled:
        return RedirectResponse(f"{settings.app_base_url}/login?error=google_disabled", 302)
    state = secrets.token_urlsafe(24)
    pkce = google_oauth.new_pkce()
    url = google_oauth.authorization_url(
        redirect_uri=settings.google_login_redirect_uri,
        state=state,
        code_challenge=pkce.challenge,
    )
    response = RedirectResponse(url, 302)
    response.set_cookie(
        GOOGLE_STATE_COOKIE,
        security.sign_state({"state": state, "verifier": pkce.verifier}),
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=GOOGLE_STATE_PATH,
    )
    return response


@router.get("/google/callback", response_class=RedirectResponse, status_code=302)
async def google_callback(
    request: Request,
    db: DbSession,
    client: Client,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()

    def fail(reason: str) -> RedirectResponse:
        resp = RedirectResponse(f"{settings.app_base_url}/login?error={reason}", 302)
        resp.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_PATH)
        return resp

    stored = security.read_state(request.cookies.get(GOOGLE_STATE_COOKIE, ""))
    if error or not code or not state or stored is None:
        return fail("google_cancelled" if error else "google_state")
    if not secrets.compare_digest(str(stored.get("state", "")), state):
        return fail("google_state")

    try:
        token_payload = await google_oauth.exchange_code(
            code=code,
            redirect_uri=settings.google_login_redirect_uri,
            code_verifier=str(stored["verifier"]),
        )
        info = await google_oauth.fetch_userinfo(str(token_payload["access_token"]))
        user = await auth_service.login_with_google(db, info)
        tokens = await auth_service.start_session(db, user, client)
    except (google_oauth.GoogleOAuthError, AppError, KeyError) as exc:
        log.warning("google_login_failed", error_type=type(exc).__name__)
        await db.rollback()
        return fail("google_failed")

    target = "/jobs" if user.onboarding_step == OnboardingStep.DONE else "/onboarding"
    response = RedirectResponse(f"{settings.app_base_url}{target}", 302)
    response.delete_cookie(GOOGLE_STATE_COOKIE, path=GOOGLE_STATE_PATH)
    set_session_cookies(response, tokens)
    return response
