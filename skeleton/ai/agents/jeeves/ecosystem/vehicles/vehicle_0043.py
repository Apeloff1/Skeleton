"""Vehicle 0043.
"""
from __future__ import annotations

VEHICLE = "vehicle_0043"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (43 % 20), "armor": 5 + (43 % 10), "seats": 1 + (43 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
