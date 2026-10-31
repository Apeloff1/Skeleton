"""Vehicle 0078.
"""
from __future__ import annotations

VEHICLE = "vehicle_0078"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (78 % 20), "armor": 5 + (78 % 10), "seats": 1 + (78 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
