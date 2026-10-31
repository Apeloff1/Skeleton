"""Vehicle 0075.
"""
from __future__ import annotations

VEHICLE = "vehicle_0075"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (75 % 20), "armor": 5 + (75 % 10), "seats": 1 + (75 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
