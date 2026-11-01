"""Key ultimate 0283.
"""
from __future__ import annotations

ID = "key_ultimate_0283"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "key"}
