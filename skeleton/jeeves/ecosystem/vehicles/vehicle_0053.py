"""Vehicle 0053.
"""
from __future__ import annotations

VEHICLE = "vehicle_0053"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (53 % 20), "armor": 5 + (53 % 10), "seats": 1 + (53 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
