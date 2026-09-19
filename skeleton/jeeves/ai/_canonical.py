"""Internal bounded canonical-JSON primitives for Jeeves control-plane records."""
from __future__ import annotations

from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

MAX_TEXT = 8192
MAX_NESTING = 12
MAX_ITEMS = 4096


def bounded_text(value: str, name: str = "text", *, max_length: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise ValueError(f"invalid {name}")
    return value


def detached_json(value: Any, *, depth: int = 0) -> Any:
    """Return a detached, finite JSON value with deterministic structural bounds."""
    if depth > MAX_NESTING:
        raise ValueError("JSON nesting too deep")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        if len(value) > MAX_TEXT or "\x00" in value:
            raise ValueError("invalid JSON text")
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite JSON number")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_ITEMS:
            raise ValueError("too many JSON mapping items")
        out: dict[str, Any] = {}
        for key, item in value.items():
            if len(out) >= MAX_ITEMS and key not in out:
                raise ValueError("too many JSON mapping items")
            bounded_text(key, "JSON key")
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = detached_json(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_ITEMS:
            raise ValueError("too many JSON sequence items")
        return [detached_json(item, depth=depth + 1) for item in value]
    raise ValueError(f"unsupported JSON type: {type(value).__name__}")


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze an already-detached JSON tree."""
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def canonical_bytes(value: Any, *, max_bytes: int) -> bytes:
    encoded = json.dumps(
        detached_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("JSON payload too large")
    return encoded


def canonical_digest(value: Any, *, max_bytes: int) -> str:
    return sha256(canonical_bytes(value, max_bytes=max_bytes)).hexdigest()


def frozen_mapping(value: Mapping[str, Any], *, max_bytes: int) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("payload must be a mapping")
    detached = detached_json(value)
    canonical_bytes(detached, max_bytes=max_bytes)
    return _deep_freeze(detached)
