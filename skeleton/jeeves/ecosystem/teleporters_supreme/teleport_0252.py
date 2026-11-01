"""Teleport supreme 0252.
"""
from __future__ import annotations

ID = "teleport_supreme_0252"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "teleport"}
