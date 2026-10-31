"""Vehicle 0004.
"""
from __future__ import annotations

VEHICLE = "vehicle_0004"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (4 % 20), "armor": 5 + (4 % 10), "seats": 1 + (4 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
