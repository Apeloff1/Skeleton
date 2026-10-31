"""Vehicle 0059.
"""
from __future__ import annotations

VEHICLE = "vehicle_0059"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (59 % 20), "armor": 5 + (59 % 10), "seats": 1 + (59 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
