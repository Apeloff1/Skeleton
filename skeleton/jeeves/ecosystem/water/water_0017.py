"""Water 0017.
"""
from __future__ import annotations

WATER = "water_0017"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (17 % 5)}
