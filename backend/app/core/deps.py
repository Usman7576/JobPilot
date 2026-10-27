from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import Unauthorized
from app.db.session import get_db
from app.models import User
from app.providers.mailer import Mailer, get_mailer
from app.services.auth_service import ClientInfo

DbSession = Annotated[AsyncSession, Depends(get_db)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


def _access_token(request: Request) -> str | None:
    token = request.cookies.get(security.ACCESS_COOKIE)
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def get_current_user(request: Request, db: DbSession) -> User:
    token = _access_token(request)
    claims = security.decode_access_token(token) if token else None
    if claims is None:
        raise Unauthorized()
    user = await db.get(User, claims.user_id)
    if user is None or not user.is_active or user.deletion_requested_at is not None:
        raise Unauthorized()
    return user


def client_info(request: Request) -> ClientInfo:
    # uvicorn runs with --proxy-headers, so request.client is the real client behind the
    # Next.js proxy (only trusted proxies may set X-Forwarded-For).
    ip = request.client.host if request.client else None
    return ClientInfo(user_agent=request.headers.get("user-agent"), ip=ip)


CurrentUser = Annotated[User, Depends(get_current_user)]
Client = Annotated[ClientInfo, Depends(client_info)]
