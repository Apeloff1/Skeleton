"""Siege 0000.
"""
from __future__ import annotations

SIEGE = "siege_0000"

def assault(strength: int) -> dict:
    return {"ok": True, "siege": SIEGE, "strength": strength, "breach": strength > 50}
