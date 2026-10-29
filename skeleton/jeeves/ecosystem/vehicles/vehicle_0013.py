"""Vehicle 0013.
"""
from __future__ import annotations

VEHICLE = "vehicle_0013"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (13 % 20), "armor": 5 + (13 % 10), "seats": 1 + (13 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
