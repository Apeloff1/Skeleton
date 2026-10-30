"""Faction mega 0048.
"""
from __future__ import annotations

ID = "faction_mega_0048"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 48, "tier": 48 % 5}

def apply(context: str = "") -> dict:
    if not context and 48 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
