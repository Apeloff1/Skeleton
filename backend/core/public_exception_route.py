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


class PublicExceptionRoute(APIRoute):
    """Apply one exception custody policy to *all* paths through a router."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def protected(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError:
                # Keep FastAPI's structured 422 validation response intact.
                raise
            except StarletteHTTPException as exc:
                # A 5xx HTTPException can still contain a caught database,
                # network, filesystem or credential-bearing exception in its
                # detail or headers. Explicit server errors need the same
                # redaction contract as unexpected exceptions.
                if exc.status_code >= 500:
                    _logger.warning(
                        "server HTTP failure at %s (status=%s)",
                        self.path,
                        exc.status_code,
                    )
                    # Never forward arbitrary error headers: a legacy route
                    # may use X-Debug or Set-Cookie to expose private state.
                    raise StarletteHTTPException(
                        status_code=exc.status_code,
                        detail=PUBLIC_INTERNAL_ERROR,
                    ) from None
                # Existing public 4xx protocol and validation behavior remain.
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
