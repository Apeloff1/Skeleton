"""Vehicle 0028.
"""
from __future__ import annotations

VEHICLE = "vehicle_0028"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (28 % 20), "armor": 5 + (28 % 10), "seats": 1 + (28 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
