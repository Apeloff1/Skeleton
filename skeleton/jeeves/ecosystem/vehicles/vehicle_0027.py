"""Vehicle 0027.
"""
from __future__ import annotations

VEHICLE = "vehicle_0027"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (27 % 20), "armor": 5 + (27 % 10), "seats": 1 + (27 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
