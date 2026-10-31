"""Vehicle 0063.
"""
from __future__ import annotations

VEHICLE = "vehicle_0063"

def stats() -> dict:
    return {"id": VEHICLE, "speed": 10 + (63 % 20), "armor": 5 + (63 % 10), "seats": 1 + (63 % 4)}

def can_mount(player: str) -> bool:
    return bool(player)
