"""Faction mega 0011.
"""
from __future__ import annotations

ID = "faction_mega_0011"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 11, "tier": 11 % 5}

def apply(context: str = "") -> dict:
    if not context and 11 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
