"""Faction mega 0089.
"""
from __future__ import annotations

ID = "faction_mega_0089"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 89, "tier": 89 % 5}

def apply(context: str = "") -> dict:
    if not context and 89 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
