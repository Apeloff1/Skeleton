"""Vehicle 0032.
"""
from __future__ import annotations

VEHICLE = "vehicle_0032"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (32 % 20), "armor": 5 + (32 % 10), "seats": 1 + (32 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
