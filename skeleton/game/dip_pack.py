"""Named dips."""

from __future__ import annotations

from typing import Any


class DipPackError(ValueError):
    pass


DIP = tuple(f"dp_{i:02d}" for i in range(12))


def dunk(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DIP:
        raise DipPackError(name)
    nxt = dict(state)
    nxt["dip"] = name
    nxt["coat"] = int(nxt.get("coat", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
