"""Faction mega 0228.
"""
from __future__ import annotations

ID = "faction_mega_0228"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 228, "tier": 228 % 5}

def apply(context: str = "") -> dict:
    if not context and 228 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
