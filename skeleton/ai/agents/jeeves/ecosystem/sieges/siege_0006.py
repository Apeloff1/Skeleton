"""Siege 0006.
"""
from __future__ import annotations

SIEGE = "siege_0006"

def assault(strength: int) -> dict:
    return {"ok": True, "siege": SIEGE, "strength": strength, "breach": strength > 50}
