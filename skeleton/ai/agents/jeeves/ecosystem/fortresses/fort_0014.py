"""Fortress 0014.
"""
from __future__ import annotations

FORT = "fort_0014"

def defense() -> int:
    return 40 + (14 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
