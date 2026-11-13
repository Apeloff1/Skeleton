"""Vehicle 0029.
"""
from __future__ import annotations

VEHICLE = "vehicle_0029"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (29 % 20), "armor": 5 + (29 % 10), "seats": 1 + (29 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
