"""Water 0025.
"""
from __future__ import annotations

WATER = "water_0025"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (25 % 5)}
