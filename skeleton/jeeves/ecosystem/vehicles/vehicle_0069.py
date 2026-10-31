"""Vehicle 0069.
"""
from __future__ import annotations

VEHICLE = "vehicle_0069"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (69 % 20), "armor": 5 + (69 % 10), "seats": 1 + (69 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
