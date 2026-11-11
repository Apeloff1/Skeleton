"""Public HTTP error helpers — never stringify caught exceptions into responses."""
from __future__ import annotations

import logging
import math
import re
from inspect import isawaitable
from itertools import islice
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("codedock.http_errors")

PUBLIC_INTERNAL_ERROR = "internal server error"
REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "credential",
    "credentials",
    "session",
    "session_token",
    "session_key",
    "client_key",
    "private_key",
    "x_api_key",
    "api_secret",
    "id_token",
    "jwt",
    "bearer",
}

_AUTHORIZATION_RE = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*(?:(?:basic|bearer)\s+)?[^\s,;]+"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password)"
    r"\b\s*[:=]\s*([^\s,;&#}]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:token|access[-_]?token|refresh[-_]?token|session|"
    r"api[-_]?key|secret|password|code|client[-_]?secret)=)[^&#\s]+"
)
_JSON_SECRET_RE = re.compile(
    r'(?i)"(?:token|password|secret|authorization|api[_-]?key|'
    r'access[_-]?token|refresh[_-]?token)"\s*:\s*"[^"\r\n]*"'
)
_MAX_REDACTED_TEXT = 16_384


def redact_client_text(value: str, *, max_len: int = 2000) -> str:
    """Bound before pattern matching, including JSON and URL credential forms.

    Inputs may contain hostile network error bodies or exception traces. Never
    regex-scan unbounded text, and never serialize unknown objects to text.
    """
    if not isinstance(value, str):
        return "[UNSUPPORTED]"
    if type(max_len) is not int or not 0 <= max_len <= _MAX_REDACTED_TEXT:
        raise ValueError("redaction character budget exceeds maximum")
    # Include a bounded lookahead to redact credentials crossing the output
    # boundary; processing is capped even for gigabyte-sized exceptions.
    text = value[:max_len + 256]
    text = _AUTHORIZATION_RE.sub(f"authorization={REDACTED}", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}", text
    )
    text = _QUERY_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{REDACTED}", text
    )
    text = _JSON_SECRET_RE.sub(REDACTED, text)
    # Do not split the redaction marker at the output budget: that can
    # turn an otherwise redacted value into a misleading partial token.
    result = text[:max_len]
    if result.endswith("[REDACT"):
        result = result[:-7]
    return result


def redact_client_payload(value: Any, *, depth: int = 0, max_depth: int = 4) -> Any:
    """Never run arbitrary object repr/getters or allocate unbounded key lists."""
    if depth >= max_depth:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return redact_client_text(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in islice(value.items(), 50):
            if not isinstance(key, str) or key in {"__proto__", "prototype", "constructor"}:
                continue
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS:
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_client_payload(
                    child, depth=depth + 1, max_depth=max_depth
                )
        return redacted
    if isinstance(value, (list, tuple)):
        return [
            redact_client_payload(child, depth=depth + 1, max_depth=max_depth)
            for child in islice(value, 50)
        ]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if not isinstance(value, float) or math.isfinite(value) else None
    return "[UNSUPPORTED]"


def public_http_error(
    status_code: int,
    public_detail: str,
    exc: BaseException | None = None,
) -> HTTPException:
    """Stable public HTTP error. Logs the exception type, never the text."""
    if exc is not None:
        log.warning(
            "public failure %s (%s): %s", status_code, public_detail, type(exc).__name__
        )
    return HTTPException(status_code=status_code, detail=public_detail)


def internal_http_error(public_detail: str, exc: BaseException | None = None) -> HTTPException:
    """Stable 500 for caught failures. Logs the exception type, never the text."""
    return public_http_error(500, public_detail, exc)


def install_public_error_handlers(app: FastAPI) -> None:
    """Register fail-closed handlers for explicit 5xx and unhandled failures.

    Starlette considers HTTPException a handled exception, not an unexpected
    failure. Protecting only Exception leaves explicit 500/502/503 route
    details and their headers untouched. Preserve the registered 4xx handler.
    """
    previous_http_handler = app.exception_handlers.get(
        StarletteHTTPException, http_exception_handler
    )

    @app.exception_handler(StarletteHTTPException)
    async def public_http_exception_handler(
        request: Any, exc: StarletteHTTPException
    ) -> Any:
        if exc.status_code < 500:
            result = previous_http_handler(request, exc)
            return await result if isawaitable(result) else result
        # Do not include the public path, arbitrary detail, or upstream
        # headers; all of these may contain network/provider credentials.
        log.warning("server HTTP failure (%s)", exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": PUBLIC_INTERNAL_ERROR},
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Any, exc: Exception) -> JSONResponse:
        log.warning("unhandled exception: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": PUBLIC_INTERNAL_ERROR},
        )
