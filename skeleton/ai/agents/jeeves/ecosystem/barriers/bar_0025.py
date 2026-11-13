"""Barrier 0025.
"""
from __future__ import annotations

BAR = "bar_0025"

def blocks(energy: float) -> dict:
    return {"ok": True, "bar": BAR, "open": energy >= 1.0, "energy": energy}
