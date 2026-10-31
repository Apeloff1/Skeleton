"""Vehicle 0020.
"""
from __future__ import annotations

VEHICLE = "vehicle_0020"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (20 % 20), "armor": 5 + (20 % 10), "seats": 1 + (20 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
