"""Vehicle 0016.
"""
from __future__ import annotations

VEHICLE = "vehicle_0016"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (16 % 20), "armor": 5 + (16 % 10), "seats": 1 + (16 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
