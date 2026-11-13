"""Vehicle 0022.
"""
from __future__ import annotations

VEHICLE = "vehicle_0022"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (22 % 20), "armor": 5 + (22 % 10), "seats": 1 + (22 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
