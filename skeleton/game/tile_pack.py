"""Named tile ticks."""

from __future__ import annotations

from typing import Any


class TilePackError(ValueError):
    pass


TILES: dict[str, tuple[int, int]] = {
    "floor": (0, 0), "vent": (2, 0), "ash": (1, 1), "fog": (0, 2), "lock": (0, 0),
    "heat": (3, 0), "extract": (0, 0), "spawn": (0, 0), "stair": (0, 0), "shaft": (1, 0),
    "bridge": (0, 0), "dead": (-1, 1), "cycle": (1, 0), "water": (-2, 1), "coil": (1, 0),
    "scrap": (0, 0), "bait": (0, 1), "dream": (0, 2), "seal": (0, 0), "crowd": (1, 1),
    "quiet": (-1, 0), "loud": (2, 0), "ward": (-1, 0), "warp": (0, 0),
}


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TILES:
        raise TilePackError(name)
    dh, df = TILES[name]
    nxt = dict(state)
    nxt["tile"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + dh))
    nxt["los_pen"] = max(0, min(8, int(nxt.get("los_pen", 0)) + df))
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in TILES:
        raise TilePackError(name)
    dh, _df = TILES[name]
    nxt = dict(state)
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((t % 3) - 1) + (dh // 2)))
    nxt["stored_prose"] = 0
    return nxt
