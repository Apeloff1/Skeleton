"""Vehicle 0011.
"""
from __future__ import annotations

VEHICLE = "vehicle_0011"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (11 % 20), "armor": 5 + (11 % 10), "seats": 1 + (11 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
