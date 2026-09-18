"""Public HTTP error helpers — never stringify caught exceptions into responses."""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

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
}

_AUTHORIZATION_RE = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*(?:(?:basic|bearer)\s+)?[^\s,;]+"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password)"
    r"\b\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def redact_client_text(value: str, *, max_len: int = 2000) -> str:
    """Redact credential-shaped text before it is stored or returned."""
    text = _AUTHORIZATION_RE.sub(f"authorization={REDACTED}", value)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}", text
    )
    if len(text) > max_len:
        return text[:max_len]
    return text


def redact_client_payload(value: Any, *, depth: int = 0, max_depth: int = 4) -> Any:
    """Bounded redaction for nested crash/telemetry payloads."""
    if depth >= max_depth:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return redact_client_text(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in list(value.items())[:50]:
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS:
                redacted[str(key)] = REDACTED
            else:
                redacted[str(key)] = redact_client_payload(
                    child, depth=depth + 1, max_depth=max_depth
                )
        return redacted
    if isinstance(value, list):
        return [
            redact_client_payload(child, depth=depth + 1, max_depth=max_depth)
            for child in value[:50]
        ]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_client_text(str(value), max_len=200)


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
    """Register a fail-closed handler for unhandled exceptions."""

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Any, exc: Exception) -> JSONResponse:
        log.warning("unhandled exception: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": PUBLIC_INTERNAL_ERROR},
        )
