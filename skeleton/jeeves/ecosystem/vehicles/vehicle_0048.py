"""Vehicle 0048.
"""
from __future__ import annotations

VEHICLE = "vehicle_0048"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (48 % 20), "armor": 5 + (48 % 10), "seats": 1 + (48 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
