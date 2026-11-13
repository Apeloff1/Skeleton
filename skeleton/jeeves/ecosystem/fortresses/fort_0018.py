"""Fortress 0018.
"""
from __future__ import annotations

FORT = "fort_0018"

def defense() -> int:
    return 40 + (18 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
