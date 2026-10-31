"""Fortress 0022.
"""
from __future__ import annotations

FORT = "fort_0022"

def defense() -> int:
    return 40 + (22 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
