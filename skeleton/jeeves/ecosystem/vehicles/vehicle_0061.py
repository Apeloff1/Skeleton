"""Vehicle 0061.
"""
from __future__ import annotations

VEHICLE = "vehicle_0061"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (61 % 20), "armor": 5 + (61 % 10), "seats": 1 + (61 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
