"""Ambient event 0043.
"""
from __future__ import annotations

EVENT = "ambient_0043"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
