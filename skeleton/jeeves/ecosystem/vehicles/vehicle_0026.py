"""Vehicle 0026.
"""
from __future__ import annotations

VEHICLE = "vehicle_0026"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (26 % 20), "armor": 5 + (26 % 10), "seats": 1 + (26 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
