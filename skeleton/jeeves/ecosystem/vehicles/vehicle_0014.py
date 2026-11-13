"""Vehicle 0014.
"""
from __future__ import annotations

VEHICLE = "vehicle_0014"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (14 % 20), "armor": 5 + (14 % 10), "seats": 1 + (14 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
