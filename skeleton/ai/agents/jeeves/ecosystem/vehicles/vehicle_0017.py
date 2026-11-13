"""Vehicle 0017.
"""
from __future__ import annotations

VEHICLE = "vehicle_0017"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (17 % 20), "armor": 5 + (17 % 10), "seats": 1 + (17 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
