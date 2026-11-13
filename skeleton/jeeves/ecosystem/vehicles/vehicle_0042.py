"""Vehicle 0042.
"""
from __future__ import annotations

VEHICLE = "vehicle_0042"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (42 % 20), "armor": 5 + (42 % 10), "seats": 1 + (42 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
