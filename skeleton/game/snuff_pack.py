"""Named snuffs."""

from __future__ import annotations

from typing import Any


class SnuffPackError(ValueError):
    pass


SNUFF = tuple(f"sn_{i:02d}" for i in range(12))


def pinch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SNUFF:
        raise SnuffPackError(name)
    nxt = dict(state)
    nxt["snuff"] = name
    nxt["light"] = max(0, int(nxt.get("light", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
