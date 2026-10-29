"""Ambient event 0017.
"""
from __future__ import annotations

EVENT = "ambient_0017"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
