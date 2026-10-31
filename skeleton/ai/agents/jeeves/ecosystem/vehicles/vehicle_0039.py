"""Vehicle 0039.
"""
from __future__ import annotations

VEHICLE = "vehicle_0039"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (39 % 20), "armor": 5 + (39 % 10), "seats": 1 + (39 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
