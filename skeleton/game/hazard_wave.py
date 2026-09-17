"""Wave-4 extra hazards."""

from __future__ import annotations

from typing import Any


class HazardWaveError(ValueError):
    pass


HAZ = tuple(f"haz_{i:02d}" for i in range(20))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAZ:
        raise HazardWaveError(name)
    nxt = dict(state)
    nxt["hazard"] = name
    nxt["hp"] = max(0, int(nxt.get("hp", 40)) - (HAZ.index(name) % 3))
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in HAZ:
        raise HazardWaveError(name)
    i = HAZ.index(name)
    nxt = dict(state)
    nxt["alert"] = int(nxt.get("alert", 0)) + (i % 2)
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) + ((t + i) % 3) - 1)
    nxt["stored_prose"] = 0
    return nxt


def leave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HAZ:
        raise HazardWaveError(name)
    nxt = dict(state)
    nxt["hazard"] = ""
    nxt["stored_prose"] = 0
    return nxt
