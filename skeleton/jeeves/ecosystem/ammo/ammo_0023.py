"""Ammo type 0023.
"""
from __future__ import annotations

AMMO = "ammo_0023"

def consume(have: int, need: int = 1) -> dict:
    if have < need:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "ammo": AMMO, "left": have - need}
