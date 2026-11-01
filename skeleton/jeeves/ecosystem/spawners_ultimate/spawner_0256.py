"""Spawner ultimate 0256.
"""
from __future__ import annotations

ID = "spawner_ultimate_0256"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "spawner"}
