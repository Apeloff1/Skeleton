"""Faction mega 0221.
"""
from __future__ import annotations

ID = "faction_mega_0221"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 221, "tier": 221 % 5}

def apply(context: str = "") -> dict:
    if not context and 221 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
