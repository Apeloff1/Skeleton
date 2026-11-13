"""Elevator 0007.
"""
from __future__ import annotations

ELEV = "elev_0007"

def go_to(floor: int) -> dict:
    if floor < 0:
        return {"ok": False, "reason": "bad_floor"}
    return {"ok": True, "elev": ELEV, "floor": floor}
