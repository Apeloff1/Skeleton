"""Vehicle 0040.
"""
from __future__ import annotations

VEHICLE = "vehicle_0040"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (40 % 20), "armor": 5 + (40 % 10), "seats": 1 + (40 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
