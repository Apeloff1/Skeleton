"""Vehicle 0070.
"""
from __future__ import annotations

VEHICLE = "vehicle_0070"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (70 % 20), "armor": 5 + (70 % 10), "seats": 1 + (70 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
