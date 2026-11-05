"""Fortress 0025.
"""
from __future__ import annotations

FORT = "fort_0025"

def defense() -> int:
    return 40 + (25 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
