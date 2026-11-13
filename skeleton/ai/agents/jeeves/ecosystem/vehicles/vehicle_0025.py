"""Vehicle 0025.
"""
from __future__ import annotations

VEHICLE = "vehicle_0025"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (25 % 20), "armor": 5 + (25 % 10), "seats": 1 + (25 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
