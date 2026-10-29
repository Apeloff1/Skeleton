"""Terrain 0038.
"""
from __future__ import annotations

TERRAIN = "terrain_0038"

def height(x: float, y: float) -> float:
    return round((x * 0.1 + y * 0.07 + 38) % 10, 2)

def walkable(h: float) -> bool:
    return 0 < h < 8
