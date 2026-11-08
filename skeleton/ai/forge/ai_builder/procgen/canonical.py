"""Canonical encoding so the same seed yields byte-identical output.

Floats are quantized to a fixed number of decimals before encoding; ``-0.0``
is folded to ``0.0`` so sign-of-zero noise never changes a digest.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from .errors import ProcgenError

DECIMALS = 6


def q(value: float, decimals: int = DECIMALS) -> float:
    if not math.isfinite(value):
        raise ProcgenError("non-finite value in generator output")
    out = round(float(value), decimals)
    return 0.0 if out == 0 else out


def normalize(obj: Any) -> Any:
    """Recursively quantize floats and turn tuples/sets into lists."""
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        return q(obj)
    if isinstance(obj, Mapping):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ProcgenError(f"non-string key {k!r}")
            out[k] = normalize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(normalize(v) for v in obj)
    raise ProcgenError(f"cannot encode {type(obj).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(normalize(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
