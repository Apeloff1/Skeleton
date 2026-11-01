"""Guild supreme 0283.
"""
from __future__ import annotations

ID = "guild_supreme_0283"

def activate(actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no_actor"}
    return {"ok": True, "id": ID, "actor": actor, "result": "activated"}

def describe() -> dict:
    return {"id": ID, "kind": "guild"}
