"""Teleport eco_supreme 0311.
"""
from __future__ import annotations

ID = "teleport_eco_supreme_0311"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "teleport"}
