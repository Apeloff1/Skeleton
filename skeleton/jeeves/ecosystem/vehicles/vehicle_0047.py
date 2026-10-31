"""Vehicle 0047.
"""
from __future__ import annotations

VEHICLE = "vehicle_0047"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (47 % 20), "armor": 5 + (47 % 10), "seats": 1 + (47 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
