"""Vehicle 0051.
"""
from __future__ import annotations

VEHICLE = "vehicle_0051"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (51 % 20), "armor": 5 + (51 % 10), "seats": 1 + (51 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
