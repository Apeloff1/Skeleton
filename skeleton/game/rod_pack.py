"""Named survey rods."""

from __future__ import annotations

from typing import Any


class RodPackError(ValueError):
    pass


ROD = tuple(f"rd_{i:02d}" for i in range(12))


def set_rod(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ROD:
        raise RodPackError(name)
    nxt = dict(state)
    nxt["rod"] = name
    nxt["stored_prose"] = 0
    return nxt
