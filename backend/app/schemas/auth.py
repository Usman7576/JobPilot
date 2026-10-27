from __future__ import annotations

import uuid
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import EmailStr, Field, StringConstraints, field_validator

from app.models.enums import OnboardingStep
from app.schemas.common import ApiModel

Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
Token = Annotated[str, StringConstraints(min_length=10, max_length=256)]


class SignupIn(ApiModel):
    email: EmailStr
    password: Password
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )


class LoginIn(ApiModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(max_length=128)]


class VerifyEmailIn(ApiModel):
    token: Token


class ResendVerificationIn(ApiModel):
    email: EmailStr


class ForgotPasswordIn(ApiModel):
    email: EmailStr


class ResetPasswordIn(ApiModel):
    token: Token
    password: Password


class AuthConfigOut(ApiModel):
    google_login_enabled: bool
    require_email_verification: bool


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    email_verified: bool
    timezone: str
    onboarding_step: OnboardingStep
    daily_send_cap: int
    follow_up_days: int
    has_password: bool


class UserUpdate(ApiModel):
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )
    timezone: str | None = None
    daily_send_cap: int | None = Field(default=None, ge=1)
    follow_up_days: int | None = Field(default=None, ge=1, le=60)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError("unknown timezone")
        return v
