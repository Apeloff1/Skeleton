"""Vehicle 0074.
"""
from __future__ import annotations

VEHICLE = "vehicle_0074"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (74 % 20), "armor": 5 + (74 % 10), "seats": 1 + (74 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
