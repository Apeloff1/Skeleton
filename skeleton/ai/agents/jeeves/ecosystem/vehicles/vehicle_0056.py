"""Vehicle 0056.
"""
from __future__ import annotations

VEHICLE = "vehicle_0056"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (56 % 20), "armor": 5 + (56 % 10), "seats": 1 + (56 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
