"""Vehicle 0005.
"""
from __future__ import annotations

VEHICLE = "vehicle_0005"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (5 % 20), "armor": 5 + (5 % 10), "seats": 1 + (5 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
