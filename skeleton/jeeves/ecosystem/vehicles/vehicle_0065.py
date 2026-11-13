"""Vehicle 0065.
"""
from __future__ import annotations

VEHICLE = "vehicle_0065"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (65 % 20), "armor": 5 + (65 % 10), "seats": 1 + (65 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
