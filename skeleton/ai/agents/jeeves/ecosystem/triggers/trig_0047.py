"""Trigger 0047.
"""
from __future__ import annotations

TRIG = "trig_0047"

def fire(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "trig": TRIG, "actor": actor, "event": "fired"}
