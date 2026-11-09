"""Canonical encoding and hashing for deterministic simulation state.

This module deliberately does not rely on pickle, repr(), platform locale, or
hash iteration order.  Every supported value is tagged by type before encoding
so values such as ``1``, ``1.0``, ``True`` and ``"1"`` cannot alias.  Floats
are finite-only and use their exact IEEE-754 binary64 representation.

The resulting byte stream is suitable for state digests, replay evidence,
snapshot integrity checks and content-addressed fixtures.  It is not intended
as a general purpose wire protocol.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
from collections.abc import Mapping, Sequence, Set
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from .errors import ValidationError

MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_ITEMS = 100_000
MAX_CANONICAL_STRING_BYTES = 4 * 1024 * 1024
MAX_CANONICAL_BYTES = 16 * 1024 * 1024


def _ensure_depth(depth: int) -> None:
    if depth > MAX_CANONICAL_DEPTH:
        raise ValidationError(
            "canonical value exceeds maximum nesting depth",
            context={"maximum": MAX_CANONICAL_DEPTH},
        )


def _ensure_text(value: str) -> str:
    raw = value.encode("utf-8")
    if len(raw) > MAX_CANONICAL_STRING_BYTES:
        raise ValidationError(
            "canonical string exceeds byte bound",
            context={"maximum": MAX_CANONICAL_STRING_BYTES},
        )
    return value


def _float_hex(value: float) -> str:
    if not math.isfinite(value):
        raise ValidationError("non-finite floats are not canonical")
    return struct.pack("!d", value).hex()


def canonical_node(value: Any, *, _depth: int = 0) -> Any:
    """Convert a supported Python value into an explicitly typed JSON node.

    Supported primitives are ``None``, ``bool``, ``int``, finite ``float``,
    ``str``, bytes-like values, enums, dataclasses, mappings, sequences,
    tuples/frozensets/sets.  Mapping keys must be strings.

    Sets are sorted by their encoded canonical nodes.  List and tuple identity
    stays distinct because both are tagged.
    """

    _ensure_depth(_depth)

    if value is None:
        return ["none"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        return ["float64", _float_hex(value)]
    if isinstance(value, str):
        return ["str", _ensure_text(value)]
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        if len(data) > MAX_CANONICAL_BYTES:
            raise ValidationError(
                "canonical byte payload exceeds bound",
                context={"maximum": MAX_CANONICAL_BYTES},
            )
        return ["bytes", base64.b64encode(data).decode("ascii")]
    if isinstance(value, Enum):
        return [
            "enum",
            value.__class__.__module__,
            value.__class__.__qualname__,
            canonical_node(value.value, _depth=_depth + 1),
        ]
    if is_dataclass(value) and not isinstance(value, type):
        return [
            "dataclass",
            value.__class__.__module__,
            value.__class__.__qualname__,
            canonical_node(asdict(value), _depth=_depth + 1),
        ]
    if isinstance(value, Mapping):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise ValidationError(
                "canonical mapping exceeds item bound",
                context={"maximum": MAX_CANONICAL_ITEMS},
            )
        rows = []
        for key in sorted(value):
            if not isinstance(key, str):
                raise ValidationError("canonical mapping keys must be strings")
            rows.append(
                [
                    _ensure_text(key),
                    canonical_node(value[key], _depth=_depth + 1),
                ]
            )
        return ["map", rows]
    if isinstance(value, tuple):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise ValidationError("canonical tuple exceeds item bound")
        return [
            "tuple",
            [canonical_node(item, _depth=_depth + 1) for item in value],
        ]
    if isinstance(value, list):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise ValidationError("canonical list exceeds item bound")
        return [
            "list",
            [canonical_node(item, _depth=_depth + 1) for item in value],
        ]
    if isinstance(value, (set, frozenset)):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise ValidationError("canonical set exceeds item bound")
        nodes = [canonical_node(item, _depth=_depth + 1) for item in value]
        nodes.sort(key=lambda item: json.dumps(item, separators=(",", ":"), ensure_ascii=False))
        tag = "frozenset" if isinstance(value, frozenset) else "set"
        return [tag, nodes]
    if isinstance(value, Sequence):
        if len(value) > MAX_CANONICAL_ITEMS:
            raise ValidationError("canonical sequence exceeds item bound")
        return [
            "sequence",
            value.__class__.__module__,
            value.__class__.__qualname__,
            [canonical_node(item, _depth=_depth + 1) for item in value],
        ]

    raise ValidationError(
        "unsupported value in canonical encoding",
        context={"type": f"{type(value).__module__}.{type(value).__qualname__}"},
    )


def canonical_json(value: Any) -> str:
    """Return stable compact JSON for a supported value."""

    return json.dumps(
        canonical_node(value),
        separators=(",", ":"),
        ensure_ascii=False,
        sort_keys=False,
    )


def canonical_bytes(value: Any) -> bytes:
    """Return UTF-8 canonical bytes."""

    return canonical_json(value).encode("utf-8")


def digest_bytes(data: bytes, *, algorithm: str = "sha256") -> str:
    if algorithm != "sha256":
        raise ValidationError("only sha256 is supported", context={"algorithm": algorithm})
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    """Return the SHA-256 digest of a canonical value."""

    return digest_bytes(canonical_bytes(value))


def digest_many(values: Sequence[Any]) -> str:
    """Hash a sequence with length-prefix framing.

    This is useful for event/replay chains where concatenating raw bytes would
    otherwise be ambiguous.
    """

    hasher = hashlib.sha256()
    for value in values:
        encoded = canonical_bytes(value)
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
    return hasher.hexdigest()


def chained_digest(previous: str, value: Any) -> str:
    """Extend a digest chain in a domain-separated way."""

    if not isinstance(previous, str) or len(previous) != 64:
        raise ValidationError("previous digest must be a sha256 hex string")
    try:
        bytes.fromhex(previous)
    except ValueError as exc:
        raise ValidationError("previous digest is not hexadecimal") from exc
    return digest({"domain": "skeleton.simulation.ecs.chain.v1", "previous": previous, "value": value})
