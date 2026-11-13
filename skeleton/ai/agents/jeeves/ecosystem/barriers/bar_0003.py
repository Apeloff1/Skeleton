"""Barrier 0003.
"""
from __future__ import annotations

BAR = "bar_0003"

def blocks(energy: float) -> dict:
    return {"ok": True, "bar": BAR, "open": energy >= 1.0, "energy": energy}
