"""Vehicle 0036.
"""
from __future__ import annotations

VEHICLE = "vehicle_0036"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (36 % 20), "armor": 5 + (36 % 10), "seats": 1 + (36 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
