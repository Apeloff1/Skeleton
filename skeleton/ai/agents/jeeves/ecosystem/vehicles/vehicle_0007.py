"""Vehicle 0007.
"""
from __future__ import annotations

VEHICLE = "vehicle_0007"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (7 % 20), "armor": 5 + (7 % 10), "seats": 1 + (7 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
