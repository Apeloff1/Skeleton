"""Vehicle 0077.
"""
from __future__ import annotations

VEHICLE = "vehicle_0077"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (77 % 20), "armor": 5 + (77 % 10), "seats": 1 + (77 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
