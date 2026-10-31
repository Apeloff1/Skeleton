"""Vehicle 0035.
"""
from __future__ import annotations

VEHICLE = "vehicle_0035"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (35 % 20), "armor": 5 + (35 % 10), "seats": 1 + (35 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
