"""Vehicle 0057.
"""
from __future__ import annotations

VEHICLE = "vehicle_0057"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (57 % 20), "armor": 5 + (57 % 10), "seats": 1 + (57 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
