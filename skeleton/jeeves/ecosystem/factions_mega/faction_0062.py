"""Faction mega 0062.
"""
from __future__ import annotations

ID = "faction_mega_0062"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 62, "tier": 62 % 5}

def apply(context: str = "") -> dict:
    if not context and 62 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
