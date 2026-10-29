"""Vehicle 0023.
"""
from __future__ import annotations

VEHICLE = "vehicle_0023"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (23 % 20), "armor": 5 + (23 % 10), "seats": 1 + (23 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
