"""Bounded, duplicate-key-rejecting, non-float canonical JSON for custody."""
from __future__ import annotations
import hashlib
import json
import unicodedata
from typing import Any

class ContractError(ValueError):
    """An untrusted contract is invalid, ambiguous or over limits."""

def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError("duplicate JSON key")
        value[key] = item
    return value

def _reject_constant(value: str) -> None:
    raise ContractError("non-finite JSON number")

def _validate(value: Any, depth: int, budget: list[int]) -> None:
    budget[0] -= 1
    if budget[0] < 0 or depth > 40:
        raise ContractError("JSON structure exceeds node/depth limit")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if not -(1 << 63) <= value < (1 << 63):
            raise ContractError("integer outside signed 64-bit range")
        return
    if type(value) is float:
        raise ContractError("floating-point JSON forbidden in authoritative records")
    if isinstance(value, str):
        if len(value) > 65536 or unicodedata.normalize("NFC", value) != value:
            raise ContractError("non-normalized or oversized Unicode")
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ContractError("surrogate Unicode character")
        return
    if isinstance(value, list):
        if len(value) > 100000:
            raise ContractError("oversized JSON array")
        for item in value:
            _validate(item, depth + 1, budget)
        return
    if isinstance(value, dict):
        if len(value) > 100000:
            raise ContractError("oversized JSON object")
        for key, item in value.items():
            if type(key) is not str:
                raise ContractError("JSON key must be string")
            _validate(key, depth + 1, budget)
            _validate(item, depth + 1, budget)
        return
    raise ContractError("unsupported authoritative JSON value")

def canonical_bytes(value: Any, *, max_bytes: int = 1048576) -> bytes:
    if type(max_bytes) is not int or not 1 <= max_bytes <= 16777216:
        raise ContractError("invalid JSON size ceiling")
    _validate(value, 0, [250000])
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContractError("JSON encoding failed") from exc
    if len(raw) > max_bytes:
        raise ContractError("canonical JSON exceeds size ceiling")
    return raw

def strict_loads(raw: bytes | str, *, max_bytes: int = 1048576) -> Any:
    if not isinstance(raw, (bytes, str)):
        raise ContractError("JSON input must be bytes or str")
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > max_bytes:
            raise ContractError("JSON input exceeds size ceiling")
        value = json.loads(encoded.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=_reject_constant)
        canonical_bytes(value, max_bytes=max_bytes)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("invalid JSON input") from exc

def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def tagged_hash(label: str, payload: bytes) -> str:
    if not isinstance(label, str) or not label.isascii() or len(label) > 80:
        raise ContractError("invalid domain-separation label")
    if not isinstance(payload, bytes) or len(payload) > 16777216:
        raise ContractError("invalid digest payload")
    return hashlib.sha256(label.encode("ascii") + b"\x00" + payload).hexdigest()
