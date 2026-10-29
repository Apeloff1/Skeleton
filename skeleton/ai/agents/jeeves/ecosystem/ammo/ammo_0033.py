"""Ammo type 0033.
"""
from __future__ import annotations

AMMO = "ammo_0033"

def consume(have: int, need: int = 1) -> dict:
    if have < need:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "ammo": AMMO, "left": have - need}
