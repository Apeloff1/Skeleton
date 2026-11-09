"""Ambient event 0001.
"""
from __future__ import annotations

EVENT = "ambient_0001"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
