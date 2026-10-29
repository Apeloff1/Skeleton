"""Terrain 0052.
"""
from __future__ import annotations

TERRAIN = "terrain_0052"

def height(x: float, y: float) -> float:
    return round((x * 0.1 + y * 0.07 + 52) % 10, 2)

def walkable(h: float) -> bool:
    return 0 < h < 8
