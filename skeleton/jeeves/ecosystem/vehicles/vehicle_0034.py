"""Vehicle 0034.
"""
from __future__ import annotations

VEHICLE = "vehicle_0034"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (34 % 20), "armor": 5 + (34 % 10), "seats": 1 + (34 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
