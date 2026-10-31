"""Vehicle 0049.
"""
from __future__ import annotations

VEHICLE = "vehicle_0049"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (49 % 20), "armor": 5 + (49 % 10), "seats": 1 + (49 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
