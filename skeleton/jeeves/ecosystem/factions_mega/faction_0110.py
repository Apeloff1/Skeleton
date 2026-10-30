"""Faction mega 0110.
"""
from __future__ import annotations

ID = "faction_mega_0110"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 110, "tier": 110 % 5}

def apply(context: str = "") -> dict:
    if not context and 110 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
