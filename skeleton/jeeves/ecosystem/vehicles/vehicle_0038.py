"""Vehicle 0038.
"""
from __future__ import annotations

VEHICLE = "vehicle_0038"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (38 % 20), "armor": 5 + (38 % 10), "seats": 1 + (38 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
