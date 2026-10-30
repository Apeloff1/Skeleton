"""Chest scale 0090.
"""
from __future__ import annotations

ID = "chest_scale_0090"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "chest"}
