"""Water 0027.
"""
from __future__ import annotations

WATER = "water_0027"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (27 % 5)}
