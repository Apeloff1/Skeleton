"""Fortress 0013.
"""
from __future__ import annotations

FORT = "fort_0013"

def defense() -> int:
    return 40 + (13 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
