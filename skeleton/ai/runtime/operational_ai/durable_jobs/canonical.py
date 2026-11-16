"""Canonical JSON and resource caps for job receipts, identities and audit."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any
from .errors import JobDenied, deny

MAX_BYTES = 131072


def validate(value: Any, depth: int = 0) -> None:
    """Bound the whole tree before materializing JSON; reject cycles and subclasses."""
    remaining = MAX_BYTES
    active: set[int] = set()

    def charge(amount: int) -> None:
        nonlocal remaining
        remaining -= amount
        if remaining < 0:
            deny("json-oversize")

    def text_budget(text: str, maximum: int, code: str) -> None:
        if type(text) is not str or len(text) > maximum:
            deny(code)
        charge(len(text) + 2)
        if any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            deny(code)

    def visit(item: Any, level: int) -> None:
        if level > 20:
            deny("json-depth")
        kind = type(item)
        if item is None:
            charge(4)
        elif kind is bool:
            charge(4 if item else 5)
        elif kind is int:
            if item.bit_length() > 128:
                deny("json-integer")
            charge(len(str(item)))
        elif kind is float:
            if not math.isfinite(item):
                deny("json-float")
            charge(1)
        elif kind is str:
            text_budget(item, 65536, "json-text")
        elif kind in (list, tuple, dict):
            if len(item) > (512 if kind is dict else 4096):
                deny("json-map" if kind is dict else "json-array")
            charge(2 + max(0, len(item)-1))
            if len(item) > remaining:
                deny("json-oversize")
            identity = id(item)
            if identity in active:
                deny("json-cycle")
            active.add(identity)
            try:
                if kind is dict:
                    for key, child in item.items():
                        text_budget(key, 128, "json-key")
                        charge(1)
                        visit(child, level+1)
                else:
                    for child in item:
                        visit(child, level+1)
            finally:
                active.remove(identity)
        else:
            deny("json-type")

    visit(value, depth)


def encode(value: Any) -> bytes:
    validate(value)
    result = bytearray()
    try:
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                                   sort_keys=True, separators=(",", ":"))
        for text in encoder.iterencode(value):
            piece = text.encode("utf-8")
            if len(piece) > MAX_BYTES - len(result):
                deny("json-oversize")
            result.extend(piece)
    except JobDenied:
        raise
    except (UnicodeError, TypeError, ValueError, RecursionError, OverflowError):
        deny("json-encoding")
    return bytes(result)


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

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            deny("json-nonfinite")
        if parsed == 0.0 and any(c in "123456789" for c in value.lower().split("e", 1)[0]):
            deny("json-float-underflow")
        return parsed

    def nonfinite(_):
        deny("json-nonfinite")

    try:
        parsed = json.loads(data.decode("utf-8", errors="strict"),
                            object_pairs_hook=pairs, parse_constant=nonfinite,
                            parse_float=finite_float)
    except JobDenied:
        raise
    except (UnicodeError, ValueError, RecursionError, OverflowError):
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
