"""Water 0040.
"""
from __future__ import annotations

WATER = "water_0040"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (40 % 5)}
