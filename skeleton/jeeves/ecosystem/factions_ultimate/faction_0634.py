"""Faction ultimate 0634.
"""
from __future__ import annotations

ID = "faction_ultimate_0634"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 634, "tier": 634 % 5}

def apply(context: str = "") -> dict:
    if not context and 634 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
