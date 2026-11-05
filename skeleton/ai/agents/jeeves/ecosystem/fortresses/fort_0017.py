"""Fortress 0017.
"""
from __future__ import annotations

FORT = "fort_0017"

def defense() -> int:
    return 40 + (17 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
