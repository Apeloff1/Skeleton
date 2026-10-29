"""Ambient event 0058.
"""
from __future__ import annotations

EVENT = "ambient_0058"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
