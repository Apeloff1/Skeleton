"""Ambient event 0037.
"""
from __future__ import annotations

EVENT = "ambient_0037"

def trigger(chance: float) -> dict:
    fired = chance > 0.5
    return {"ok": True, "event": EVENT, "fired": fired}
