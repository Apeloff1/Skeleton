"""Minimum-necessary telemetry envelope, enforced independently of clients.

Untrusted telemetry is not a general-purpose error dump or a vehicle for user
content. Preserve categorical and numeric diagnostics only. Do not persist
exception text, stack traces, query payloads, arbitrary strings or credentials.
"""

from __future__ import annotations

import math
import re
from typing import Any

SAFE_EVENTS = frozenset({
    "open", "close", "nav", "warn", "error", "fatal", "crash",
    "metric", "custom", "other",
})
SAFE_STRING_FIELDS = frozenset({
    "status", "state", "phase", "kind", "mode", "unit", "result",
})
SAFE_ENUMS = frozenset({
    "ok", "success", "failed", "failure", "error", "warning",
    "pending", "queued", "running", "started", "stopped",
    "completed", "cancelled", "canceled", "timeout", "retrying",
    "skipped", "unknown", "available", "unavailable", "healthy",
    "unhealthy", "connected", "disconnected", "offline", "online",
    "enabled", "disabled", "valid", "invalid", "open", "closed",
    "visible", "hidden", "primary", "secondary", "local", "remote",
    "web", "native", "android", "ios", "desktop", "macos",
    "windows", "linux", "dev", "test", "prod", "development",
    "production", "zip", "apk", "pdf", "json", "text", "image",
    "audio", "video", "python", "javascript", "typescript",
    "seconds", "milliseconds", "bytes", "count", "percent",
})
SAFE_ERROR_NAMES = frozenset({
    "Error", "TypeError", "ReferenceError", "RangeError", "SyntaxError",
    "URIError", "EvalError", "AggregateError", "NetworkError",
    "AbortError", "TimeoutError",
})
DENIED_KEY = re.compile(
    r"token|secret|pass|auth|cookie|credential|session|identity|"
    r"user|name|email|phone|address|location|url|uri|path|stack|"
    r"message|prompt|code|query|body|payload|header|account|card|"
    r"pin|key|client|response|request|text|value|content|ip",
    re.IGNORECASE,
)
LABEL_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]*\Z", re.ASCII)
EVENT_ACTION_RE = re.compile(r"action:[A-Za-z][A-Za-z0-9_-]{0,47}\Z", re.ASCII)
FIELD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z", re.ASCII)
SESSION_RE = re.compile(
    r"s_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z",
    re.ASCII | re.IGNORECASE,
)


def safe_label(value: Any, max_length: int = 80) -> str:
    if type(value) is not str or not 1 <= len(value) <= max_length:
        return "unknown"
    return value if LABEL_RE.fullmatch(value) else "unknown"


def safe_event(value: Any) -> str:
    if type(value) is not str:
        return "other"
    if value in SAFE_EVENTS or EVENT_ACTION_RE.fullmatch(value):
        return value
    return "other"


def safe_session(value: Any) -> str:
    if type(value) is str and SESSION_RE.fullmatch(value):
        return value
    return "unknown"


def safe_number(value: Any, *, maximum: float, allow_zero: bool = True) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        numeric = float(value)
    except (TypeError, OverflowError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0 or numeric > maximum:
        return None
    if not allow_zero and numeric == 0:
        return None
    return numeric


def safe_detail(value: Any) -> dict[str, str | int | float | bool] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, str | int | float | bool] = {}
    # Bound work and never traverse arbitrary values or nested structures.
    for key in list(value)[:24]:
        if type(key) is not str or len(key) > 40 or not FIELD_RE.fullmatch(key):
            continue
        if DENIED_KEY.search(key):
            continue
        entry = value[key]
        if type(entry) is bool:
            out[key] = entry
        elif type(entry) in (int, float):
            number = safe_number(entry, maximum=1_000_000_000)
            if number is not None:
                out[key] = number
        elif type(entry) is str:
            if key in SAFE_STRING_FIELDS and entry.lower() in SAFE_ENUMS:
                out[key] = entry.lower()
            elif key == "error_type" and entry in SAFE_ERROR_NAMES:
                out[key] = entry
    return out or None


def crash_metadata(
    *,
    source: Any,
    component: Any,
    message: Any,
    stack: Any,
    info: Any,
    app_version: Any,
) -> dict[str, Any]:
    # Classify whether diagnostics existed, never what they contained.
    return {
        "source_present": bool(source),
        "component_present": bool(component),
        "message_present": bool(message),
        "stack_present": bool(stack),
        "info": safe_detail(info),
        "app_version_present": bool(app_version),
    }
