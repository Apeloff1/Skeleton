"""Faction mega 0032.
"""
from __future__ import annotations

ID = "faction_mega_0032"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 32, "tier": 32 % 5}

def apply(context: str = "") -> dict:
    if not context and 32 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
