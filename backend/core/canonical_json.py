"""Strict canonical JSON primitives for portable cryptographic identities.

Security-sensitive hashes must not depend on Python-only coercions. These helpers
accept only JSON-compatible values, reject non-finite floats and non-string object
keys, serialize deterministically, and provide a round-trip snapshot primitive for
removing caller-owned mutable aliases before durable persistence.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class CanonicalJSONError(ValueError):
    """Raised when a value cannot participate in portable canonical JSON."""


def _validate(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJSONError(f"non-finite number at {path}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError(f"non-string object key at {path}")
            _validate(item, path=f"{path}.{key}")
        return
    raise CanonicalJSONError(f"unsupported JSON value at {path}: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON or fail closed on non-portable values."""
    _validate(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalJSONError("value cannot be encoded as canonical JSON") from exc


def canonical_json_text(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_json_clone(value: Any) -> Any:
    """Detach a JSON value from caller-owned containers using the canonical form."""
    return json.loads(canonical_json_bytes(value))
