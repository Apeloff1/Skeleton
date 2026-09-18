"""Telemetry redaction helpers shared by logging, tracing, health, and events."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"

SENSITIVE_KEYS = frozenset({
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
})
_SENSITIVE_KEYS = SENSITIVE_KEYS
_AUTHORIZATION_RE = re.compile(
    r"(?i)\bauthorization\b\s*[:=]\s*(?:(?:basic|bearer)\s+)?[^\s,;]+"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password)"
    r"\b\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def _normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def redact_text(value: str) -> str:
    """Redact common inline credential shapes while preserving safe context."""
    value = _AUTHORIZATION_RE.sub(f"authorization={REDACTED}", value)
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    return _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}", value
    )


def redact_payload(value: Any, *, max_depth: int = 8) -> Any:
    """Return a bounded telemetry-safe copy of nested payload data."""
    if isinstance(max_depth, bool) or not isinstance(max_depth, int):
        raise TypeError("max_depth must be an integer")
    if max_depth < 1:
        raise ValueError("max_depth must be at least 1")

    def visit(item: Any, depth: int, key: object | None = None) -> Any:
        if key is not None and _normalize_key(key) in _SENSITIVE_KEYS:
            return REDACTED
        if depth >= max_depth:
            return TRUNCATED
        if isinstance(item, str):
            return redact_text(item)
        if isinstance(item, Mapping):
            return {
                str(child_key): visit(child_value, depth + 1, child_key)
                for child_key, child_value in item.items()
            }
        if isinstance(item, tuple):
            return tuple(visit(child, depth + 1) for child in item)
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, set):
            return sorted((visit(child, depth + 1) for child in item), key=repr)
        return item

    return visit(value, 0)


def safe_exception_text(error: BaseException) -> str:
    """Return stable diagnostics without persisting arbitrary exception text."""
    return type(error).__name__