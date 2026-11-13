"""Ambient event 0041.
"""
from __future__ import annotations

EVENT = "ambient_0041"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
