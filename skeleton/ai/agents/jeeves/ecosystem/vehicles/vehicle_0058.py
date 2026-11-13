"""Vehicle 0058.
"""
from __future__ import annotations

VEHICLE = "vehicle_0058"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (58 % 20), "armor": 5 + (58 % 10), "seats": 1 + (58 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
