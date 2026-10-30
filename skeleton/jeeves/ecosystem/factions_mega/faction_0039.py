"""Faction mega 0039.
"""
from __future__ import annotations

ID = "faction_mega_0039"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 39, "tier": 39 % 5}

def apply(context: str = "") -> dict:
    if not context and 39 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
