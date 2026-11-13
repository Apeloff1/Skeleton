"""Vehicle 0054.
"""
from __future__ import annotations

VEHICLE = "vehicle_0054"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (54 % 20), "armor": 5 + (54 % 10), "seats": 1 + (54 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
