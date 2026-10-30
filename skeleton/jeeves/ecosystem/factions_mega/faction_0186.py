"""Faction mega 0186.
"""
from __future__ import annotations

ID = "faction_mega_0186"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 186, "tier": 186 % 5}

def apply(context: str = "") -> dict:
    if not context and 186 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
