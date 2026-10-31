"""Vehicle 0001.
"""
from __future__ import annotations

VEHICLE = "vehicle_0001"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (1 % 20), "armor": 5 + (1 % 10), "seats": 1 + (1 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
