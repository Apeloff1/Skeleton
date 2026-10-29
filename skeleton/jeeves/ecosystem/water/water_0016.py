"""Water 0016.
"""
from __future__ import annotations

WATER = "water_0016"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (16 % 5)}
