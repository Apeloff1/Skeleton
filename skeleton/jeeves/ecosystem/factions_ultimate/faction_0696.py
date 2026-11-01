"""Faction ultimate 0696.
"""
from __future__ import annotations

ID = "faction_ultimate_0696"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 696, "tier": 696 % 5}

def apply(context: str = "") -> dict:
    if not context and 696 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
