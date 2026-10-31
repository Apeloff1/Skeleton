"""Elevator 0013.
"""
from __future__ import annotations

ELEV = "elev_0013"

def go_to(floor: int) -> dict:
    if floor < 0:
        return {"ok": False, "reason": "bad_floor"}
    return {"ok": True, "elev": ELEV, "floor": floor}
