"""Fortress 0020.
"""
from __future__ import annotations

FORT = "fort_0020"

def defense() -> int:
    return 40 + (20 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
