"""Ambient event 0077.
"""
from __future__ import annotations

EVENT = "ambient_0077"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
