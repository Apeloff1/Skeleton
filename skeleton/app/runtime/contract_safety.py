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


def normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def is_secret_key(key: object) -> bool:
    return normalize_key(key) in SENSITIVE_KEYS


def safe_public_message(message: str, *, limit: int = MAX_PUBLIC_MESSAGE_CHARS) -> str:
    cleaned = redact_text(str(message or ""))
    if len(cleaned) > limit:
        return cleaned[:limit] + "…"
    return cleaned


def _bound_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= MAX_OUTPUT_DEPTH:
        return TRUNCATED
    if isinstance(value, str):
        redacted = redact_text(value)
        if len(redacted) > MAX_OUTPUT_STRING_CHARS:
            return redacted[:MAX_OUTPUT_STRING_CHARS] + "…"
        return redacted
    if isinstance(value, Mapping):
        bounded: dict[str, Any] = {}
        for raw_key, raw_item in list(value.items())[:MAX_OUTPUT_LIST_ITEMS]:
            key = str(raw_key)
            if is_secret_key(key):
                bounded[key] = REDACTED
            else:
                bounded[key] = _bound_value(raw_item, depth=depth + 1)
        return bounded
    if isinstance(value, tuple):
        return tuple(_bound_value(item, depth=depth + 1) for item in value[:MAX_OUTPUT_LIST_ITEMS])
    if isinstance(value, list):
        return [_bound_value(item, depth=depth + 1) for item in value[:MAX_OUTPUT_LIST_ITEMS]]
    if isinstance(value, set):
        return sorted(
            (_bound_value(item, depth=depth + 1) for item in list(value)[:MAX_OUTPUT_LIST_ITEMS]),
            key=repr,
        )
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else TRUNCATED
    return redact_text(str(value))[:MAX_OUTPUT_STRING_CHARS]


def public_contract_payload(value: Any) -> Any:
    """Return a redacted, size-bounded copy safe to emit on CLI/API surfaces."""

    bounded = _bound_value(redact_payload(value, max_depth=MAX_OUTPUT_DEPTH))
    encoded = json.dumps(bounded, sort_keys=True, default=str, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= MAX_OUTPUT_BYTES:
        return bounded
    return {"truncated": True, "reason": "output_too_large"}