"""Vehicle 0076.
"""
from __future__ import annotations

VEHICLE = "vehicle_0076"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (76 % 20), "armor": 5 + (76 % 10), "seats": 1 + (76 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
