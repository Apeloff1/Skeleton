"""Interactable 0000.
"""
from __future__ import annotations

PROP = "prop_0000"

def interact(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "prop": PROP, "actor": actor, "result": "used"}
