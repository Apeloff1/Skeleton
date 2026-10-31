"""Vehicle 0000.
"""
from __future__ import annotations

VEHICLE = "vehicle_0000"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (0 % 20), "armor": 5 + (0 % 10), "seats": 1 + (0 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
