"""Vehicle 0002.
"""
from __future__ import annotations

VEHICLE = "vehicle_0002"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (2 % 20), "armor": 5 + (2 % 10), "seats": 1 + (2 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
