"""Faction mega 0181.
"""
from __future__ import annotations

ID = "faction_mega_0181"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 181, "tier": 181 % 5}

def apply(context: str = "") -> dict:
    if not context and 181 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
