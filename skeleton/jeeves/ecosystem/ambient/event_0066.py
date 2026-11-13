"""Ambient event 0066.
"""
from __future__ import annotations

EVENT = "ambient_0066"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
