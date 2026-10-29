"""Water 0028.
"""
from __future__ import annotations

WATER = "water_0028"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (28 % 5)}
