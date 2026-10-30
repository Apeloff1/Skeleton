"""Faction mega 0128.
"""
from __future__ import annotations

ID = "faction_mega_0128"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 128, "tier": 128 % 5}

def apply(context: str = "") -> dict:
    if not context and 128 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
