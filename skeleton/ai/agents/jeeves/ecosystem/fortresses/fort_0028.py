"""Fortress 0028.
"""
from __future__ import annotations

FORT = "fort_0028"

def defense() -> int:
    return 40 + (28 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
