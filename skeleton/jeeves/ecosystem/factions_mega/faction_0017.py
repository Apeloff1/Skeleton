"""Faction mega 0017.
"""
from __future__ import annotations

ID = "faction_mega_0017"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 17, "tier": 17 % 5}

def apply(context: str = "") -> dict:
    if not context and 17 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
