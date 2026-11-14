"""Bounded canonical JSON; reject ambiguous keys, nonfinite numbers and depth."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any
from .errors import deny

MAX_JSON = 8 * 1024 * 1024
MAX_TEXT = 65536
_ID = re.compile(r"[a-z][a-z0-9_-]{0,127}\Z", re.ASCII)
_SHA = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)


def identity(value: Any, name: str = "id") -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        deny(name + "-invalid")
    return value


def sha(value: Any, name: str = "sha") -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        deny(name + "-invalid")
    return value


def number(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        deny(name + "-range")
    return value


def string(value: Any, name: str, maximum: int = MAX_TEXT) -> str:
    if type(value) is not str or len(value) > maximum:
        deny(name + "-text")
    if any(ord(c) < 32 and c not in "\t\n" for c in value):
        deny(name + "-control")
    if any(0xd800 <= ord(c) <= 0xdfff for c in value):
        deny(name + "-unicode")
    return value


def _inspect(value: Any, depth: int = 0) -> None:
    if depth > 24:
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
        string(value, "json-string")
        return
    if type(value) in (tuple, list):
        if len(value) > 65536:
            deny("json-array")
        for item in value:
            _inspect(item, depth + 1)
        return
    if isinstance(value, Mapping):
        if len(value) > 512:
            deny("json-object")
        for key, item in value.items():
            if type(key) is not str or not 1 <= len(key) <= 128:
                deny("json-key")
            _inspect(item, depth + 1)
        return
    deny("json-type")


def encode(value: Any) -> bytes:
    _inspect(value)
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        deny("json-encoding")
    if len(raw) > MAX_JSON:
        deny("json-oversize")
    return raw


def decode(raw: bytes | str) -> Any:
    if type(raw) is str:
        try:
            raw = raw.encode("utf-8")
        except UnicodeError:
            deny("json-encoding")
    if type(raw) is not bytes or len(raw) > MAX_JSON:
        deny("json-oversize")
    def pairs(items: list[tuple[str, Any]]) -> dict:
        value = {}
        for key, item in items:
            if key in value:
                deny("json-duplicate")
            value[key] = item
        return value
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=lambda _: deny("json-nonfinite"))
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        deny("json-invalid")
    _inspect(result)
    return result


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def bytes_sha(data: bytes) -> str:
    if type(data) is not bytes:
        deny("bytes-required")
    return hashlib.sha256(data).hexdigest()
