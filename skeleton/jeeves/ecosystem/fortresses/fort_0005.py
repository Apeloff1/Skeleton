"""Fortress 0005.
"""
from __future__ import annotations

FORT = "fort_0005"

def defense() -> int:
    return 40 + (5 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
