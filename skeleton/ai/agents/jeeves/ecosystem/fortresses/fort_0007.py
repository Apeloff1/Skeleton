"""Fortress 0007.
"""
from __future__ import annotations

FORT = "fort_0007"

def defense() -> int:
    return 40 + (7 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
