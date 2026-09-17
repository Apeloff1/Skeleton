"""Named dye baths."""

from __future__ import annotations

from typing import Any


class BathPackError(ValueError):
    pass


BATH = tuple(f"bh_{i:02d}" for i in range(12))


def set_bath(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BATH:
        raise BathPackError(name)
    nxt = dict(state)
    nxt["bath"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
