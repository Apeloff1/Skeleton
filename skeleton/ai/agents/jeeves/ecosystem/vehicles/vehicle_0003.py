"""Vehicle 0003.
"""
from __future__ import annotations

VEHICLE = "vehicle_0003"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (3 % 20), "armor": 5 + (3 % 10), "seats": 1 + (3 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
