"""Vehicle 0066.
"""
from __future__ import annotations

VEHICLE = "vehicle_0066"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (66 % 20), "armor": 5 + (66 % 10), "seats": 1 + (66 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
