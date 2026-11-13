"""Vehicle 0037.
"""
from __future__ import annotations

VEHICLE = "vehicle_0037"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (37 % 20), "armor": 5 + (37 % 10), "seats": 1 + (37 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
