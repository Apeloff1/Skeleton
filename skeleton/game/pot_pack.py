"""Named pots."""

from __future__ import annotations

from typing import Any


class PotPackError(ValueError):
    pass


POT = tuple(f"pt_{i:02d}" for i in range(20))


def plant(state: dict[str, Any], name: str, stock: str) -> dict[str, Any]:
    if name not in POT:
        raise PotPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("pot") or {})
    cur[name] = stock
    nxt["pot"] = cur
    nxt["stored_prose"] = 0
    return nxt
