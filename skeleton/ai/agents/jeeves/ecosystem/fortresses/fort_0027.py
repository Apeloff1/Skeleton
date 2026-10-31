"""Fortress 0027.
"""
from __future__ import annotations

FORT = "fort_0027"

def defense() -> int:
    return 40 + (27 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
