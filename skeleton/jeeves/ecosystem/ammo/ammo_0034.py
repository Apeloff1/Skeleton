"""Ammo type 0034.
"""
from __future__ import annotations

AMMO = "ammo_0034"

def consume(have: int, need: int = 1) -> dict:
    if have < need:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "ammo": AMMO, "left": have - need}
