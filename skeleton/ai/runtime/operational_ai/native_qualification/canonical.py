"""Strict source manifest and benchmark result JSON: no ambiguous payloads."""
from __future__ import annotations
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any
from .errors import deny

MAX_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 24
MAX_TEXT = 65536
MAX_KEYS = 256
MAX_ARRAY = 4096


def _check(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        deny("json-depth")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if value.bit_length() > 128:
            deny("json-integer")
        return
    if type(value) is float:
        if not math.isfinite(value):
            deny("json-nonfinite")
        return
    if type(value) is str:
        if len(value) > MAX_TEXT or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            deny("json-string")
        return
    if type(value) in (tuple, list):
        if len(value) > MAX_ARRAY:
            deny("json-array")
        for x in value:
            _check(x, depth + 1)
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_KEYS:
            deny("json-object")
        for key, item in value.items():
            if type(key) is not str or not 1 <= len(key) <= 128:
                deny("json-key")
            _check(key, depth + 1)
            _check(item, depth + 1)
        return
    deny("json-type")


def encode(obj: Any) -> bytes:
    _check(obj)
    try:
        raw = json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        deny("json-encoding")
    if len(raw) > MAX_BYTES:
        deny("json-oversize")
    return raw


def decode(raw: bytes | str) -> Any:
    if type(raw) is str:
        try:
            raw = raw.encode("utf-8")
        except UnicodeError:
            deny("json-encoding")
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        deny("json-oversize")
    def pairs(items: list[tuple[str, Any]]) -> dict:
        obj = {}
        for key, value in items:
            if key in obj:
                deny("json-duplicate")
            obj[key] = value
        return obj
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                         parse_constant=lambda _: deny("json-nonfinite"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        deny("json-invalid")
    _check(obj)
    return obj


def sha256(raw: bytes) -> str:
    if type(raw) is not bytes:
        deny("sha-input")
    return hashlib.sha256(raw).hexdigest()


def identity(value: Any, label: str = "identifier") -> str:
    import re
    if type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value, re.ASCII) is None:
        deny(label + "-invalid")
    return value


def hex64(value: Any, field: str = "digest") -> str:
    import re
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value, re.ASCII) is None:
        deny(field + "-invalid")
    return value


def integer(value: Any, field: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        deny(field + "-range")
    return value


def text(value: Any, field: str, limit: int) -> str:
    if type(value) is not str or len(value) > limit or any(
        ord(c) < 32 and c not in "\n\t" for c in value
    ):
        deny(field + "-invalid")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        deny(field + "-unicode")
    return value
