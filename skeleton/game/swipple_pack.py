"""Named swipples."""

from __future__ import annotations

from typing import Any


class SwipplePackError(ValueError):
    pass


SWIPPLE = tuple(f"sw_{i:02d}" for i in range(8))


def set_swipple(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SWIPPLE:
        raise SwipplePackError(name)
    nxt = dict(state)
    nxt["swipple"] = name
    nxt["beat"] = int(nxt.get("beat", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
