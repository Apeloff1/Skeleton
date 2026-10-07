"""Canonical JSON snapshots shared by runtime and memory adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from skeleton.frontier.execution import positive_int


def json_snapshot(value: Any, *, max_bytes: int = 1_048_576) -> Any:
    """Validate JSON types, bound encoded size, and detach nested mutable data."""
    positive_int("max_bytes", max_bytes)

    def validate(item: Any, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("payload nesting exceeds 64 levels")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("payload object keys must be strings")
                validate(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                validate(child, depth + 1)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"unsupported payload type: {type(item).__name__}")

    if isinstance(value, Mapping):
        value = dict(value)
    validate(value)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > max_bytes:
            raise ValueError(f"payload exceeds {max_bytes} bytes")
        return json.loads(encoded)
    except (TypeError, OverflowError, UnicodeError) as exc:
        raise ValueError("payload must be valid JSON") from exc


def memory_payload(item: Mapping[str, Any], item_id: str, max_bytes: int) -> dict[str, Any]:
    if not isinstance(item_id, str) or not item_id.strip() or len(item_id) > 256:
        raise ValueError("memory id must be a non-empty string of at most 256 characters")
    return json_snapshot({**item, "id": item_id}, max_bytes=max_bytes)
