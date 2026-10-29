"""Vehicle 0009.
"""
from __future__ import annotations

VEHICLE = "vehicle_0009"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (9 % 20), "armor": 5 + (9 % 10), "seats": 1 + (9 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
