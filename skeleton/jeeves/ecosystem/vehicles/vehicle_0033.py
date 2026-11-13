"""Vehicle 0033.
"""
from __future__ import annotations

VEHICLE = "vehicle_0033"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (33 % 20), "armor": 5 + (33 % 10), "seats": 1 + (33 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
