"""Vehicle 0062.
"""
from __future__ import annotations

VEHICLE = "vehicle_0062"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (62 % 20), "armor": 5 + (62 % 10), "seats": 1 + (62 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
