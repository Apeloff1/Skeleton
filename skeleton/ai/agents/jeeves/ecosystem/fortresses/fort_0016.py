"""Fortress 0016.
"""
from __future__ import annotations

FORT = "fort_0016"

def defense() -> int:
    return 40 + (16 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
