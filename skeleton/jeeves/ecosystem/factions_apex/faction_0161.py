"""Faction apex 0161.
"""
from __future__ import annotations

ID = "faction_apex_0161"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 161, "tier": 161 % 5}

def apply(context: str = "") -> dict:
    if not context and 161 % 29 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
