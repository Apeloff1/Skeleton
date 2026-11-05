"""Canonical JSON and resource caps for job receipts, identities and audit."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any
from .errors import deny

MAX_BYTES = 131072


def validate(value: Any, depth: int = 0) -> None:
    if depth > 20:
        deny("json-depth")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if value.bit_length() > 128:
            deny("json-integer")
        return
    if type(value) is float:
        if not math.isfinite(value):
            deny("json-float")
        return
    if type(value) is str:
        if len(value) > 65536 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            deny("json-text")
        return
    if type(value) in (list, tuple):
        if len(value) > 4096:
            deny("json-array")
        for child in value:
            validate(child, depth+1)
        return
    if type(value) is dict:
        if len(value) > 512:
            deny("json-map")
        for key, child in value.items():
            if type(key) is not str or len(key) > 128:
                deny("json-key")
            validate(child, depth+1)
        return
    deny("json-type")


def encode(value: Any) -> bytes:
    validate(value)
    try:
        payload = json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (UnicodeError, TypeError, ValueError):
        deny("json-encoding")
    if len(payload) > MAX_BYTES:
        deny("json-oversize")
    return payload


def decode(data: bytes) -> Any:
    if type(data) is not bytes or len(data) > MAX_BYTES:
        deny("json-oversize")
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                deny("json-duplicate")
            result[name] = value
        return result
    def nonfinite(_):
        deny("json-nonfinite")
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, ValueError, RecursionError):
        deny("json-syntax")
    validate(parsed)
    return parsed


def sha256(data: bytes) -> str:
    if type(data) is not bytes:
        deny("sha-input")
    return hashlib.sha256(data).hexdigest()


def fingerprint(value: Any) -> str:
    return sha256(encode(value))


def require_sha(value: Any) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        deny("sha-invalid")
    return value


def require_int(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or value < low or value > high:
        deny("integer-"+name)
    return value


def require_text(value: Any, maximum: int, name: str, *, allow_empty: bool=False) -> str:
    if type(value) is not str or len(value) > maximum or (not allow_empty and not value):
        deny("text-"+name)
    if any(ord(c) < 32 and c not in "\n\t" for c in value) or any(0xD800<=ord(c)<=0xDFFF for c in value):
        deny("text-"+name)
    return value
