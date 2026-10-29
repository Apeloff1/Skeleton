"""Terrain 0015.
"""
from __future__ import annotations

TERRAIN = "terrain_0015"

def height(x: float, y: float) -> float:
    return round((x * 0.1 + y * 0.07 + 15) % 10, 2)

def walkable(h: float) -> bool:
    return 0 < h < 8
