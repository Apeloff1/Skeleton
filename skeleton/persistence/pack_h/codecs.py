"""Value codecs for Pack H durable storage.

Only data-safe codecs are offered: JSON (default), UTF-8 text and raw bytes.
Pickle is deliberately absent; durable rows must never execute code on read.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple


class CodecError(ValueError):
    pass


def _reject_non_finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise CodecError("non-finite floats are not durable")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise CodecError("JSON object keys must be strings")
            _reject_non_finite(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_non_finite(v)
    return value


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for storage and fingerprints."""
    _reject_non_finite(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CodecError(f"value is not JSON-serializable: {exc}") from exc


@dataclass(frozen=True, slots=True)
class Codec:
    name: str
    encode: Callable[[Any], bytes]
    decode: Callable[[bytes], Any]


def _json_encode(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def _json_decode(blob: bytes) -> Any:
    try:
        return json.loads(bytes(blob).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodecError("corrupt JSON payload") from exc


def _text_encode(value: Any) -> bytes:
    if not isinstance(value, str):
        raise CodecError("text codec requires str")
    return value.encode("utf-8")


def _text_decode(blob: bytes) -> Any:
    try:
        return bytes(blob).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CodecError("corrupt text payload") from exc


def _bytes_encode(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise CodecError("bytes codec requires bytes-like")
    return bytes(value)


JSON = Codec("json", _json_encode, _json_decode)
TEXT = Codec("text", _text_encode, _text_decode)
BYTES = Codec("bytes", _bytes_encode, lambda b: bytes(b))

REGISTRY: Dict[str, Codec] = {c.name: c for c in (JSON, TEXT, BYTES)}


def get_codec(name: str) -> Codec:
    try:
        return REGISTRY[name]
    except KeyError as exc:
        raise CodecError(f"unknown codec {name!r}") from exc


def auto_encode(value: Any) -> Tuple[str, bytes]:
    """Pick the narrowest safe codec for a value."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return BYTES.name, BYTES.encode(value)
    if isinstance(value, str):
        return TEXT.name, TEXT.encode(value)
    return JSON.name, JSON.encode(value)
