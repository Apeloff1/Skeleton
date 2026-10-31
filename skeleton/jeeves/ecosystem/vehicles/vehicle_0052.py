"""Vehicle 0052.
"""
from __future__ import annotations

VEHICLE = "vehicle_0052"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (52 % 20), "armor": 5 + (52 % 10), "seats": 1 + (52 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
