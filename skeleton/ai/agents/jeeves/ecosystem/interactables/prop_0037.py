"""Interactable 0037.
"""
from __future__ import annotations

PROP = "prop_0037"

def interact(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "prop": PROP, "actor": actor, "result": "used"}
