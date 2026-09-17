"""Named brick clamps."""

from __future__ import annotations

from typing import Any


class ClampPackError(ValueError):
    pass


CLAMP = tuple(f"cm_{i:02d}" for i in range(12))


def fire(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CLAMP:
        raise ClampPackError(name)
    nxt = dict(state)
    nxt["clamp"] = name
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 2)
    nxt["stored_prose"] = 0
    return nxt
