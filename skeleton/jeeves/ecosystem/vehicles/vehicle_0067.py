"""Vehicle 0067.
"""
from __future__ import annotations

VEHICLE = "vehicle_0067"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (67 % 20), "armor": 5 + (67 % 10), "seats": 1 + (67 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
