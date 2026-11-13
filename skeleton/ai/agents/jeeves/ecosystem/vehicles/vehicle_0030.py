"""Vehicle 0030.
"""
from __future__ import annotations

VEHICLE = "vehicle_0030"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (30 % 20), "armor": 5 + (30 % 10), "seats": 1 + (30 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
