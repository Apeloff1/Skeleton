"""Vehicle 0055.
"""
from __future__ import annotations

VEHICLE = "vehicle_0055"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (55 % 20), "armor": 5 + (55 % 10), "seats": 1 + (55 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
