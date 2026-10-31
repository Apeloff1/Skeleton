"""Ambient event 0044.
"""
from __future__ import annotations

EVENT = "ambient_0044"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
