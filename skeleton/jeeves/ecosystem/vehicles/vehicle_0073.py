"""Vehicle 0073.
"""
from __future__ import annotations

VEHICLE = "vehicle_0073"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (73 % 20), "armor": 5 + (73 % 10), "seats": 1 + (73 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
