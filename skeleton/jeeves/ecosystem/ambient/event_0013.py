"""Ambient event 0013.
"""
from __future__ import annotations

EVENT = "ambient_0013"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
