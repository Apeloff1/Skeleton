"""Named barnacle sets."""

from __future__ import annotations

from typing import Any


class BarnaclePackError(ValueError):
    pass


BARN = tuple(f"ba_{i:02d}" for i in range(16))


def grow(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BARN:
        raise BarnaclePackError(name)
    nxt = dict(node)
    nxt["barnacle"] = int(nxt.get("barnacle", 0)) + 1 + (BARN.index(name) % 2)
    nxt["stored_prose"] = 0
    return nxt
