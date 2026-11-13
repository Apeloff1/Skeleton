"""Fortress 0029.
"""
from __future__ import annotations

FORT = "fort_0029"

def defense() -> int:
    return 40 + (29 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
