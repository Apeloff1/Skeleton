"""Terrain 0001.
"""
from __future__ import annotations

TERRAIN = "terrain_0001"

def height(x: float, y: float) -> float:
    return round((x * 0.1 + y * 0.07 + 1) % 10, 2)

def walkable(h: float) -> bool:
    return 0 < h < 8
