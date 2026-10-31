"""Vehicle 0041.
"""
from __future__ import annotations

VEHICLE = "vehicle_0041"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (41 % 20), "armor": 5 + (41 % 10), "seats": 1 + (41 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
