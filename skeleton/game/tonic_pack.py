"""Named tonics."""

from __future__ import annotations

from typing import Any


class TonicPackError(ValueError):
    pass


TONIC = tuple(f"to_{i:02d}" for i in range(16))


def drink(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TONIC:
        raise TonicPackError(name)
    nxt = dict(state)
    nxt["tonic"] = name
    nxt["sleep"] = min(16, int(nxt.get("sleep", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
