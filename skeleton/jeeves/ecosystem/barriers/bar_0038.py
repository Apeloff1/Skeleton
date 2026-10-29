"""Barrier 0038.
"""
from __future__ import annotations

BAR = "bar_0038"

def blocks(energy: float) -> dict:
    return {"ok": True, "bar": BAR, "open": energy >= 1.0, "energy": energy}
