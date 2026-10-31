"""Vehicle 0064.
"""
from __future__ import annotations

VEHICLE = "vehicle_0064"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (64 % 20), "armor": 5 + (64 % 10), "seats": 1 + (64 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
