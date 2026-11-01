"""Trigger ultra_max 0212.
"""
from __future__ import annotations

ID = "trigger_ultra_max_0212"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "trigger"}
