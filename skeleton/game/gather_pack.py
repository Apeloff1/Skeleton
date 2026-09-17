"""Named gathers."""

from __future__ import annotations

from typing import Any


class GatherPackError(ValueError):
    pass


GATHER = tuple(f"gt_{i:02d}" for i in range(12))


def dip(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GATHER:
        raise GatherPackError(name)
    nxt = dict(state)
    nxt["gather"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
