"""Fortress 0008.
"""
from __future__ import annotations

FORT = "fort_0008"

def defense() -> int:
    return 40 + (8 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
