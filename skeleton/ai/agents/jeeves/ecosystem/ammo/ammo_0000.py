"""Ammo type 0000.
"""
from __future__ import annotations

AMMO = "ammo_0000"

def consume(have: int, need: int = 1) -> dict:
    if have < need:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "ammo": AMMO, "left": have - need}
