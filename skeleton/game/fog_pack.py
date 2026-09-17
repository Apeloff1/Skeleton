"""Named fog banks."""

from __future__ import annotations

from typing import Any


class FogPackError(ValueError):
    pass


FOG = (
    "thin", "wall", "drift", "pool", "shaft", "cell", "stair", "bridge",
    "extract", "spawn", "heat", "lock", "dream", "seal", "crowd", "quiet",
)


def apply(state: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in FOG:
        raise FogPackError(name)
    nxt = dict(state)
    nxt["fog_bank"] = name
    nxt["los_pen"] = max(0, min(8, FOG.index(name) % 5 + (t % 3) - 1))
    nxt["stored_prose"] = 0
    return nxt


def clear(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FOG:
        raise FogPackError(name)
    nxt = dict(state)
    if nxt.get("fog_bank") == name:
        nxt["los_pen"] = 0
        nxt["fog_bank"] = ""
    nxt["stored_prose"] = 0
    return nxt
