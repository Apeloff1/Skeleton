"""Fortress 0010.
"""
from __future__ import annotations

FORT = "fort_0010"

def defense() -> int:
    return 40 + (10 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
