"""Advanced weather 0073.
"""
from __future__ import annotations

WEATHER = "adv_weather_0073"

def intensity(t: float) -> float:
    return round(0.3 + (t % 1.0) * 0.7, 3)

def effects() -> dict:
    return {"visibility": 0.8, "move_scale": 0.9, "damage": 0 if 73 % 4 else 1}
