"""Faction ultimate 0431.
"""
from __future__ import annotations

ID = "faction_ultimate_0431"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 431, "tier": 431 % 5}

def apply(context: str = "") -> dict:
    if not context and 431 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
