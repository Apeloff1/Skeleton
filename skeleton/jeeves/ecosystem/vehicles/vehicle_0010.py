"""Vehicle 0010.
"""
from __future__ import annotations

VEHICLE = "vehicle_0010"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (10 % 20), "armor": 5 + (10 % 10), "seats": 1 + (10 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
