"""Fortress 0021.
"""
from __future__ import annotations

FORT = "fort_0021"

def defense() -> int:
    return 40 + (21 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
