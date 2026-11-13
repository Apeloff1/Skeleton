"""Barrier 0014.
"""
from __future__ import annotations

BAR = "bar_0014"

def blocks(energy: float) -> dict:
    return {"ok": True, "bar": BAR, "open": energy >= 1.0, "energy": energy}
