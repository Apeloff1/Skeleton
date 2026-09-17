"""Named veils over LOS."""

from __future__ import annotations

from typing import Any


class VeilPackError(ValueError):
    pass


VEILS = tuple(f"vl_{i:02d}" for i in range(20))


def draw(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in VEILS:
        raise VeilPackError(name)
    nxt = dict(state)
    nxt["veil"] = name
    nxt["los_pen"] = min(8, int(nxt.get("los_pen", 0)) + 1 + (VEILS.index(name) % 3))
    nxt["stored_prose"] = 0
    return nxt
