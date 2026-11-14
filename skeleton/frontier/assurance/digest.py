"""Deterministic, bounded JSON state hashing without object string coercion."""
import hashlib
import json
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

_MAX_DEPTH = 64
_MAX_NODES = 100_000
_MAX_TEXT = 1_048_576
_MAX_BYTES = 8_388_608


def normalize_state(state: Any) -> Any:
    remaining = _MAX_NODES
    text_remaining = _MAX_BYTES

    def visit(value: Any, depth: int) -> Any:
        nonlocal remaining, text_remaining
        remaining -= 1
        if remaining < 0 or depth > _MAX_DEPTH:
            raise ValueError("state structural budget exceeded")
        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            if value.bit_length() > 4096:
                raise ValueError("integer budget exceeded")
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if type(value) is str:
            if len(value) > _MAX_TEXT:
                raise ValueError("state text budget exceeded")
            text_remaining -= len(value.encode("utf-8"))
            if text_remaining < 0:
                raise ValueError("state text budget exceeded")
            return value
        if type(value) in (list, tuple):
            if len(value) > remaining:
                raise ValueError("state element budget exceeded")
            return [visit(item, depth + 1) for item in value]
        if type(value) in (dict, MappingProxyType):
            if len(value) > remaining:
                raise ValueError("state mapping budget exceeded")
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("state keys must be strings")
                result[visit(key, depth + 1)] = visit(item, depth + 1)
            return result
        raise ValueError("unsupported or non-finite state value")

    return visit(state, 0)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def freeze_state(state: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = normalize_state(state)
    if not isinstance(normalized, dict):
        raise ValueError("snapshot state must be a mapping")
    return _freeze(normalized)


def state_digest(state: Any) -> str:
    payload = json.dumps(normalize_state(state), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > _MAX_BYTES:
        raise ValueError("canonical state byte budget exceeded")
    return hashlib.sha256(payload).hexdigest()
