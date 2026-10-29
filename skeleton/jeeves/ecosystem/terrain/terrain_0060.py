"""Terrain 0060.
"""
from __future__ import annotations

TERRAIN = "terrain_0060"

def height(x: float, y: float) -> float:
    return round((x * 0.1 + y * 0.07 + 60) % 10, 2)

def walkable(h: float) -> bool:
    return 0 < h < 8
