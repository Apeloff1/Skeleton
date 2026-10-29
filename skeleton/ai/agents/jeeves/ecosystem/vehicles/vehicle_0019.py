"""Vehicle 0019.
"""
from __future__ import annotations

VEHICLE = "vehicle_0019"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (19 % 20), "armor": 5 + (19 % 10), "seats": 1 + (19 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
