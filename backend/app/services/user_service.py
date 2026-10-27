from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import User
from app.schemas.auth import UserOut, UserUpdate


class SendCapTooHigh(AppError):
    status_code, code, title = 422, "send_cap_too_high", "Daily send cap is above the maximum"


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified_at is not None,
        timezone=user.timezone,
        onboarding_step=user.onboarding_step,
        daily_send_cap=user.daily_send_cap,
        follow_up_days=user.follow_up_days,
        has_password=user.password_hash is not None,
    )


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    changes = data.model_dump(exclude_unset=True)
    cap = changes.get("daily_send_cap")
    max_cap = get_settings().max_daily_send_cap
    if cap is not None and cap > max_cap:
        raise SendCapTooHigh(f"The maximum is {max_cap} emails per day.")
    for field, value in changes.items():
        if value is not None or field == "full_name":
            setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
