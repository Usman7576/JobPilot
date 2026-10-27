"""Errors returned as RFC 9457 problem+json: {type, title, status, detail, code}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)
PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    title: str = "Bad request"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.extra = extra


class NotFound(AppError):
    status_code, code, title = 404, "not_found", "Not found"


class Unauthorized(AppError):
    status_code, code, title = 401, "unauthorized", "Not authenticated"


class Forbidden(AppError):
    status_code, code, title = 403, "forbidden", "Forbidden"


class Conflict(AppError):
    status_code, code, title = 409, "conflict", "Conflict"


class InvalidCredentials(AppError):
    status_code, code, title = 401, "invalid_credentials", "Invalid email or password"


class EmailNotVerified(AppError):
    status_code, code, title = 403, "email_not_verified", "Please verify your email first"


class InvalidToken(AppError):
    status_code, code, title = 400, "invalid_token", "This link is invalid or has expired"


class ServiceUnavailable(AppError):
    status_code, code, title = 503, "service_unavailable", "Service unavailable"


def problem(
    status_code: int, code: str, title: str, detail: str | None = None, **extra: Any
) -> JSONResponse:
    body = {
        "type": f"https://jobpilot.ai/problems/{code}",
        "title": title,
        "status": status_code,
        "detail": detail or title,
        "code": code,
        **extra,
    }
    return JSONResponse(body, status_code=status_code, media_type=PROBLEM_JSON)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return problem(exc.status_code, exc.code, exc.title, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return problem(422, "validation_error", "Invalid request", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RateLimitExceeded)
    async def _rate(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return problem(429, "rate_limited", "Too many requests", f"Limit: {exc.detail}")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return problem(500, "internal_error", "Something went wrong")
