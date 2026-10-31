"""Elevator 0010.
"""
from __future__ import annotations

ELEV = "elev_0010"

def go_to(floor: int) -> dict:
    if floor < 0:
        return {"ok": False, "reason": "bad_floor"}
    return {"ok": True, "elev": ELEV, "floor": floor}
