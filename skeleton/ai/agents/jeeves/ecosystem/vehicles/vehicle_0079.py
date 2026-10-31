"""Vehicle 0079.
"""
from __future__ import annotations

VEHICLE = "vehicle_0079"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (79 % 20), "armor": 5 + (79 % 10), "seats": 1 + (79 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
