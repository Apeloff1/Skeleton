"""Wave-4 extra tiles."""

from __future__ import annotations

from typing import Any


class TileWaveError(ValueError):
    pass


TILES = tuple(f"tile_{i:02d}" for i in range(20))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TILES:
        raise TileWaveError(name)
    nxt = dict(state)
    nxt["tile"] = name
    nxt["heat"] = max(0, min(16, int(nxt.get("heat", 0)) + ((TILES.index(name) % 5) - 2)))
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in TILES:
        raise TileWaveError(name)
    nxt = dict(state)
    nxt["los_pen"] = max(0, min(8, int(nxt.get("los_pen", 0)) + ((TILES.index(name) % 3) - 1)))
    nxt["stored_prose"] = 0
    return nxt
