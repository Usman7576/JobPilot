from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

from app.api.v1.router import api_router
from app.core import security
from app.core.config import get_settings
from app.core.errors import problem, register_error_handlers
from app.core.logging import configure_logging
from app.core.ratelimit import limiter

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _operation_id(route: APIRoute) -> str:
    # Stable, readable ids -> stable generated hook names (e.g. useAuthLogin).
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title="JobPilot AI API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.state.limiter = limiter
    register_error_handlers(app)

    @app.middleware("http")
    async def csrf_and_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Double-submit CSRF check for cookie-authenticated, state-changing requests.
        has_session_cookie = security.ACCESS_COOKIE in request.cookies or (
            security.REFRESH_COOKIE in request.cookies
        )
        if request.method in UNSAFE_METHODS and has_session_cookie:
            cookie = request.cookies.get(security.CSRF_COOKIE, "")
            header = request.headers.get(security.CSRF_HEADER, "")
            if not cookie or not secrets.compare_digest(cookie, header):
                return problem(403, "csrf_failed", "CSRF token missing or invalid")

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        response.headers["x-frame-options"] = "DENY"
        return response

    app.include_router(api_router)
    return app


app = create_app()
