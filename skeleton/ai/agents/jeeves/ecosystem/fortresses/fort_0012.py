"""Fortress 0012.
"""
from __future__ import annotations

FORT = "fort_0012"

def defense() -> int:
    return 40 + (12 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
