"""Canonical, bounded JSON protocol with duplicate-key and NaN refusal.

All durable operation identities are digests of this exact serialization; JSON
must never be used for authority if decoding silently discards duplicate keys.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from typing import Any, Mapping

MAX_ENVELOPE_BYTES = 262_144
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ContractViolation(ValueError):
    """An untrusted value crossed an explicit contract boundary."""


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, value in pairs:
        if name in data:
            raise ContractViolation(f"duplicate JSON key: {name}")
        data[name] = value
    return data


def _invalid_constant(value: str) -> None:
    raise ContractViolation(f"nonfinite JSON constant: {value}")


def load_json(raw: bytes | str, *, ceiling: int = MAX_ENVELOPE_BYTES) -> Any:
    if isinstance(raw, str):
        try:
            raw = raw.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ContractViolation("invalid Unicode envelope") from exc
    if not isinstance(raw, bytes) or type(ceiling) is not int or not 1 <= ceiling <= 32 * 1024 * 1024:
        raise ContractViolation("invalid bounded JSON input")
    if not raw or len(raw) > ceiling:
        raise ContractViolation("JSON byte limit exceeded")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=strict_pairs,
                          parse_constant=_invalid_constant)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ContractViolation("invalid canonical JSON input") from exc


def canonical_bytes(value: Any, *, ceiling: int = MAX_ENVELOPE_BYTES) -> bytes:
    if type(ceiling) is not int or not 1 <= ceiling <= 32 * 1024 * 1024:
        raise ContractViolation("invalid canonical JSON ceiling")
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             allow_nan=False, separators=(",", ":")).encode("utf-8", errors="strict")
        if not encoded or len(encoded) > ceiling:
            raise ContractViolation("canonical JSON byte budget exceeded")
        # Prevent exotic non-string keys or custom encoders changing identity.
        if json.loads(encoded.decode("utf-8"), object_pairs_hook=strict_pairs) != value:
            raise ContractViolation("non-round-trippable canonical value")
        return encoded
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ContractViolation("invalid canonical JSON value") from exc


def digest(value: Any, *, ceiling: int = MAX_ENVELOPE_BYTES) -> str:
    return hashlib.sha256(canonical_bytes(value, ceiling=ceiling)).hexdigest()


def sha256(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise ContractViolation("digest requires bytes")
    return hashlib.sha256(value).hexdigest()


def require_digest(value: object, *, field: str = "sha256") -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractViolation(f"invalid {field}")
    return value


def same_digest(left: str, right: str) -> bool:
    require_digest(left, field="left digest")
    require_digest(right, field="right digest")
    return hmac.compare_digest(left, right)


def require_mapping(value: object, *, fields: frozenset[str] | None = None) -> Mapping[str, Any]:
    if not isinstance(value, dict) or any(type(k) is not str for k in value):
        raise ContractViolation("object required")
    if fields is not None and set(value) != fields:
        raise ContractViolation("object fields do not match schema")
    return value


def require_small_text(value: object, *, field: str, maximum: int = 16384,
                       allow_empty: bool = False) -> str:
    if not isinstance(value, str) or type(value) is not str:
        raise ContractViolation(f"invalid {field}: text required")
    try:
        count = len(value.encode("utf-8", errors="strict"))
    except UnicodeError as exc:
        raise ContractViolation(f"invalid {field}: Unicode") from exc
    if count > maximum or (not allow_empty and not value.strip()):
        raise ContractViolation(f"invalid {field}: empty or oversized")
    if '\x00' in value:
        raise ContractViolation(f"invalid {field}: NUL byte")
    return value


def require_number(value: object, *, field: str, minimum: int = 0,
                   maximum: int = 2**53 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractViolation(f"invalid {field}: bounded integer required")
    return value
