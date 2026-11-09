"""Ambient event 0052.
"""
from __future__ import annotations

EVENT = "ambient_0052"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
