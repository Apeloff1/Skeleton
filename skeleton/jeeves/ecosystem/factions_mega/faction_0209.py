"""Faction mega 0209.
"""
from __future__ import annotations

ID = "faction_mega_0209"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 209, "tier": 209 % 5}

def apply(context: str = "") -> dict:
    if not context and 209 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
