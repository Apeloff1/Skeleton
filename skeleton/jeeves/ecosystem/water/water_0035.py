"""Water 0035.
"""
from __future__ import annotations

WATER = "water_0035"

def current(speed: float = 1.0) -> dict:
    return {"ok": True, "water": WATER, "speed": speed, "depth": 2 + (35 % 5)}
