"""Fortress 0006.
"""
from __future__ import annotations

FORT = "fort_0006"

def defense() -> int:
    return 40 + (6 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
