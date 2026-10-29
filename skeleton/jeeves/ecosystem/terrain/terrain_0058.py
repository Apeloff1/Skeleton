"""Terrain 0058.
"""
from __future__ import annotations

TERRAIN = "terrain_0058"

def height(x: float, y: float) -> float:
    return round((x * 0.1 + y * 0.07 + 58) % 10, 2)

def walkable(h: float) -> bool:
    return 0 < h < 8
