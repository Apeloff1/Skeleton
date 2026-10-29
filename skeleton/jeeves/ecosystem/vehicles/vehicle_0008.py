"""Vehicle 0008.
"""
from __future__ import annotations

VEHICLE = "vehicle_0008"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (8 % 20), "armor": 5 + (8 % 10), "seats": 1 + (8 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
