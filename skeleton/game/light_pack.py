"""Named lights vs LOS."""

from __future__ import annotations

from typing import Any


class LightPackError(ValueError):
    pass


LIGHTS = tuple(f"lt_{i:02d}" for i in range(20))


def on(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LIGHTS:
        raise LightPackError(name)
    nxt = dict(node)
    nxt["light"] = name
    nxt["los_pen"] = max(0, int(nxt.get("los_pen", 0)) - (1 + (LIGHTS.index(name) % 3)))
    nxt["stored_prose"] = 0
    return nxt
