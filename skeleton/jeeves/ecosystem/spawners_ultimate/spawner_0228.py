"""Spawner ultimate 0228.
"""
from __future__ import annotations

ID = "spawner_ultimate_0228"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "spawner"}
