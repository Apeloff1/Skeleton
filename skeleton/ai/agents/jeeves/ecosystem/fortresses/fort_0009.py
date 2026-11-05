"""Fortress 0009.
"""
from __future__ import annotations

FORT = "fort_0009"

def defense() -> int:
    return 40 + (9 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
