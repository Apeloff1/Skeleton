"""Vehicle 0044.
"""
from __future__ import annotations

VEHICLE = "vehicle_0044"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (44 % 20), "armor": 5 + (44 % 10), "seats": 1 + (44 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
