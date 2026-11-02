"""Trigger eco_apex 0596.
"""
from __future__ import annotations

ID = "trigger_eco_apex_0596"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "trigger"}
