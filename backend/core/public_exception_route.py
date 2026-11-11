"""Fail-closed HTTP route boundary for legacy services.

Preserve explicit HTTP errors and FastAPI request-validation responses. Unknown
exceptions are server-side only: exception messages, stack traces, provider
details, filesystem paths and credential-bearing values never enter the body.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from core.http_errors import PUBLIC_INTERNAL_ERROR

_logger = logging.getLogger("codedock.public_route")


class PublicExceptionRouteMixin:
    """Composes with APIRoute subclasses, preserving existing auth/custody guards."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def protected(request: Request) -> Response:
            try:
                return await original(request)
            except (StarletteHTTPException, RequestValidationError):
                # Preserve intentionally public status codes and FastAPI's
                # standard 422 schema. No conversion of known client errors.
                raise
            except Exception as exc:
                # Log type and route template only, never arbitrary input or
                # exception text: DB/HTTP exceptions may include credentials.
                _logger.warning(
                    "unhandled route exception at %s (%s)",
                    self.path,
                    type(exc).__name__,
                )
                raise StarletteHTTPException(
                    status_code=500, detail=PUBLIC_INTERNAL_ERROR
                ) from None

        return protected


class PublicExceptionRoute(PublicExceptionRouteMixin, APIRoute):
    """Safe default route class for routers without an existing custom class."""
