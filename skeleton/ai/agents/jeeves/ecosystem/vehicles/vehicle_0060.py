"""Vehicle 0060.
"""
from __future__ import annotations

VEHICLE = "vehicle_0060"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (60 % 20), "armor": 5 + (60 % 10), "seats": 1 + (60 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
