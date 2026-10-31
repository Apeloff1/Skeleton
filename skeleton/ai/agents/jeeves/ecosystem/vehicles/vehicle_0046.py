"""Vehicle 0046.
"""
from __future__ import annotations

VEHICLE = "vehicle_0046"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (46 % 20), "armor": 5 + (46 % 10), "seats": 1 + (46 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
