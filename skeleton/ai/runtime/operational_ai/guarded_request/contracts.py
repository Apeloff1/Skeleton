"""Bounded strict JSON used for receipts, manifests and ingress.

Duplicate keys, nonfinite numbers, deep nesting, surrogates, large objects,
non-string map keys and control-character ambiguities are fail-closed.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from .errors import deny

MAX_JSON_BYTES = 131072
MAX_DEPTH = 24
MAX_MAP_KEYS = 512
MAX_ARRAY_ITEMS = 4096
MAX_TEXT_CHARS = 32768


def _validate(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        deny("json-depth")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if value.bit_length() > 128:
            deny("json-integer")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            deny("json-nonfinite")
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT_CHARS or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            deny("json-text")
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_ARRAY_ITEMS:
            deny("json-array")
        for child in value:
            _validate(child, depth + 1)
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_MAP_KEYS:
            deny("json-object")
        for k, v in value.items():
            if type(k) is not str or len(k) > 128:
                deny("json-key")
            _validate(k, depth + 1)
            _validate(v, depth + 1)
        return
    deny("json-type")


def canonical_bytes(value: Any) -> bytes:
    _validate(value)
    try:
        data = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        deny("json-encoding")
    if len(data) > MAX_JSON_BYTES:
        deny("json-size")
    return data


def parse_json(data: bytes | str) -> Any:
    if isinstance(data, str):
        try:
            data = data.encode("utf-8")
        except UnicodeError:
            deny("json-encoding")
    if type(data) is not bytes or len(data) > MAX_JSON_BYTES:
        deny("json-size")
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result: dict[str, Any] = {}
        for k, v in items:
            if k in result:
                deny("json-duplicate")
            result[k] = v
        return result
    def constant(_: str) -> None:
        deny("json-nonfinite")
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        deny("json-syntax")
    _validate(result)
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def require_text(value: Any, *, maximum: int, field: str) -> str:
    if type(value) is not str or len(value) > maximum:
        deny(field + "-text")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        deny(field + "-control")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        deny(field + "-unicode")
    return value


def strict_integer(value: Any, *, minimum: int, maximum: int, field: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        deny(field + "-range")
    return value
