"""Vehicle 0012.
"""
from __future__ import annotations

VEHICLE = "vehicle_0012"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (12 % 20), "armor": 5 + (12 % 10), "seats": 1 + (12 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
