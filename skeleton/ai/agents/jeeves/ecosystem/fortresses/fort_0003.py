"""Fortress 0003.
"""
from __future__ import annotations

FORT = "fort_0003"

def defense() -> int:
    return 40 + (3 % 30)

def hold(attack: int) -> dict:
    d = defense()
    return {"ok": True, "fort": FORT, "held": attack < d, "defense": d}
