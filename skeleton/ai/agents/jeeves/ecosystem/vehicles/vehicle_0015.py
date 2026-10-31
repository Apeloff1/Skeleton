"""Vehicle 0015.
"""
from __future__ import annotations

VEHICLE = "vehicle_0015"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (15 % 20), "armor": 5 + (15 % 10), "seats": 1 + (15 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
