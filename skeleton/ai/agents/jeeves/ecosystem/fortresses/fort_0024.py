"""Fortress 0024.
"""
from __future__ import annotations

FORT = "fort_0024"

def defense() -> int:
    return 40 + (24 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
