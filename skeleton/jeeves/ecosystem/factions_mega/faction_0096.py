"""Faction mega 0096.
"""
from __future__ import annotations

ID = "faction_mega_0096"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 96, "tier": 96 % 5}

def apply(context: str = "") -> dict:
    if not context and 96 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
