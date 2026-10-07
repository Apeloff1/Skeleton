"""Secret-safe, size-bounded public payloads for the unified command contract.

Adapters and transports share these helpers so CLI and API cannot echo secrets
or unbounded subsystem output. This is not an orchestration layer.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from skeleton.observability.redaction import (
    REDACTED,
    SENSITIVE_KEYS,
    TRUNCATED,
    redact_payload,
    redact_text,
)

MAX_OUTPUT_DEPTH = 8
MAX_OUTPUT_LIST_ITEMS = 64
MAX_OUTPUT_STRING_CHARS = 4_096
MAX_OUTPUT_BYTES = 32_768
MAX_PUBLIC_MESSAGE_CHARS = 256
# Repository audits enumerate the complete mounted route set, which exceeds
# ordinary command output. They retain finite byte, depth and item limits.
MAX_AUDIT_ITEMS = 1_024
MAX_AUDIT_BYTES = 262_144


def normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def is_secret_key(key: object) -> bool:
    return normalize_key(key) in SENSITIVE_KEYS


def safe_public_message(message: str, *, limit: int = MAX_PUBLIC_MESSAGE_CHARS) -> str:
    cleaned = redact_text(str(message or ""))
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _bound_value(value: Any, *, depth: int = 0, max_items: int = MAX_OUTPUT_LIST_ITEMS) -> Any:
    if depth >= MAX_OUTPUT_DEPTH:
        return TRUNCATED
    if isinstance(value, str):
        redacted = redact_text(value)
        if len(redacted) > MAX_OUTPUT_STRING_CHARS:
            return redacted[:MAX_OUTPUT_STRING_CHARS] + "…"
        return redacted
    if isinstance(value, Mapping):
        bounded: dict[str, Any] = {}
        for raw_key, raw_item in list(value.items())[:max_items]:
            key = str(raw_key)
            if is_secret_key(key):
                bounded[key] = REDACTED
            else:
                bounded[key] = _bound_value(raw_item, depth=depth + 1, max_items=max_items)
        return bounded
    if isinstance(value, tuple):
        return tuple(_bound_value(item, depth=depth + 1, max_items=max_items) for item in value[:max_items])
    if isinstance(value, list):
        return [_bound_value(item, depth=depth + 1, max_items=max_items) for item in value[:max_items]]
    if isinstance(value, set):
        return sorted(
            (_bound_value(item, depth=depth + 1, max_items=max_items) for item in list(value)[:max_items]),
            key=repr,
        )
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else TRUNCATED
    return redact_text(str(value))[:MAX_OUTPUT_STRING_CHARS]


def public_contract_payload(value: Any, *, repository_audit: bool = False) -> Any:
    """Return a redacted, size-bounded copy safe to emit on CLI/API surfaces."""

    max_items = MAX_AUDIT_ITEMS if repository_audit else MAX_OUTPUT_LIST_ITEMS
    max_bytes = MAX_AUDIT_BYTES if repository_audit else MAX_OUTPUT_BYTES
    bounded = _bound_value(redact_payload(value, max_depth=MAX_OUTPUT_DEPTH), max_items=max_items)
    encoded = json.dumps(bounded, sort_keys=True, default=str, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= max_bytes:
        return bounded
    return {"truncated": True, "reason": "output_too_large"}