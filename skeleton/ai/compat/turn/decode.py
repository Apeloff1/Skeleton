"""GB-55 decode. r1 and r2 pass. r3halt only with halt=1. No sentence."""

from __future__ import annotations

_DEPTH = {"r1": 1, "r2": 2, "r3halt": 3}


def _halt(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value not in (0, 1):
        return None
    return value


def decode(depth: object, halt: object = 0) -> dict:
    bit = _halt(halt)
    token = depth if isinstance(depth, str) and depth in _DEPTH else ""
    ok = 0
    if bit is not None and token:
        ok = 1 if token != "r3halt" or bit == 1 else 0
    return {
        "kind": "decode",
        "ok": ok,
        "depth": token if ok else "",
        "halt": 0 if bit is None else bit,
        "r": _DEPTH[token] if ok else 0,
        "stored_prose": 0,
    }
