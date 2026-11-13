"""Vehicle 0071.
"""
from __future__ import annotations

VEHICLE = "vehicle_0071"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (71 % 20), "armor": 5 + (71 % 10), "seats": 1 + (71 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
