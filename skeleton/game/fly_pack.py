"""Named fly lengths."""

from __future__ import annotations

from typing import Any


class FlyPackError(ValueError):
    pass


FLY = tuple(f"fy_{i:02d}" for i in range(12))


def set_fly(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in FLY:
        raise FlyPackError(name)
    nxt = dict(state)
    nxt["fly"] = name
    nxt["span"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
