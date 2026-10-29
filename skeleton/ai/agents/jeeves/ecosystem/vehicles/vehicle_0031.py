"""Vehicle 0031.
"""
from __future__ import annotations

VEHICLE = "vehicle_0031"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (31 % 20), "armor": 5 + (31 % 10), "seats": 1 + (31 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
