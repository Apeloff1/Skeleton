"""Vehicle 0050.
"""
from __future__ import annotations

VEHICLE = "vehicle_0050"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (50 % 20), "armor": 5 + (50 % 10), "seats": 1 + (50 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
