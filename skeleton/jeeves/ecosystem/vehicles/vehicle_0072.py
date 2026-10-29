"""Vehicle 0072.
"""
from __future__ import annotations

VEHICLE = "vehicle_0072"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (72 % 20), "armor": 5 + (72 % 10), "seats": 1 + (72 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
