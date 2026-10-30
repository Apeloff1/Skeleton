"""Fortress 0000.
"""
from __future__ import annotations

FORT = "fort_0000"

def defense() -> int:
    return 40 + (0 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
