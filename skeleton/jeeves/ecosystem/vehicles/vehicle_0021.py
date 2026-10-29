"""Vehicle 0021.
"""
from __future__ import annotations

VEHICLE = "vehicle_0021"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (21 % 20), "armor": 5 + (21 % 10), "seats": 1 + (21 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
