"""Faction mega 0247.
"""
from __future__ import annotations

ID = "faction_mega_0247"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 247, "tier": 247 % 5}

def apply(context: str = "") -> dict:
    if not context and 247 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
