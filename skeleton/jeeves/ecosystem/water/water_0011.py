"""Water 0011.
"""
from __future__ import annotations

WATER = "water_0011"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (11 % 5)}
