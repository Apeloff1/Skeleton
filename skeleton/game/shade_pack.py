"""Named shade cloths."""

from __future__ import annotations

from typing import Any


class ShadePackError(ValueError):
    pass


SHADE = tuple(f"sd_{i:02d}" for i in range(12))


def draw(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHADE:
        raise ShadePackError(name)
    nxt = dict(node)
    nxt["shade"] = name
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) - 1)
    nxt["stored_prose"] = 0
    return nxt
