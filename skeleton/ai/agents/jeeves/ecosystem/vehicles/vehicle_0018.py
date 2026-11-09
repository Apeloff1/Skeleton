"""Vehicle 0018.
"""
from __future__ import annotations

VEHICLE = "vehicle_0018"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (18 % 20), "armor": 5 + (18 % 10), "seats": 1 + (18 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
