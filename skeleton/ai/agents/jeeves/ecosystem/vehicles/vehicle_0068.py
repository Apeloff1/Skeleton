"""Vehicle 0068.
"""
from __future__ import annotations

VEHICLE = "vehicle_0068"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (68 % 20), "armor": 5 + (68 % 10), "seats": 1 + (68 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
