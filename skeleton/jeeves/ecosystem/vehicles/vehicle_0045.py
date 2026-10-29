"""Vehicle 0045.
"""
from __future__ import annotations

VEHICLE = "vehicle_0045"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (45 % 20), "armor": 5 + (45 % 10), "seats": 1 + (45 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
