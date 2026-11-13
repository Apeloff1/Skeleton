"""Vehicle 0006.
"""
from __future__ import annotations

VEHICLE = "vehicle_0006"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (6 % 20), "armor": 5 + (6 % 10), "seats": 1 + (6 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
