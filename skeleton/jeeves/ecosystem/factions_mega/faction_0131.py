"""Faction mega 0131.
"""
from __future__ import annotations

ID = "faction_mega_0131"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 131, "tier": 131 % 5}

def apply(context: str = "") -> dict:
    if not context and 131 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
