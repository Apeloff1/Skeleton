"""Fog banks. LOS penalty by floor and tick."""

from __future__ import annotations

from typing import Any


class FogError(ValueError):
    pass


def fog_pen(heat: int, t: int, floor: int) -> int:
    if floor < 0 or floor > 3:
        raise FogError("floor")
    tmod = int(t) % 8
    return min(3, (int(heat) // 4) + (floor % 2) + (1 if tmod in {0, 4} else 0))


def apply_fog(state: dict[str, Any], floor: int, t: int) -> dict[str, Any]:
    nxt = dict(state)
    nxt["los_pen"] = fog_pen(int(nxt.get("heat", 0)), t, floor)
    nxt["stored_prose"] = 0
    return nxt
