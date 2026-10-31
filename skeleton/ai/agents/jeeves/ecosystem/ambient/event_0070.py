"""Ambient event 0070.
"""
from __future__ import annotations

EVENT = "ambient_0070"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
