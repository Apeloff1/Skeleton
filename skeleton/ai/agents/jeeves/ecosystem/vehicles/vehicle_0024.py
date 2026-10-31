"""Vehicle 0024.
"""
from __future__ import annotations

VEHICLE = "vehicle_0024"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (24 % 20), "armor": 5 + (24 % 10), "seats": 1 + (24 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
