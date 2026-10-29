"""Water 0000.
"""
from __future__ import annotations

WATER = "water_0000"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (0 % 5)}
