"""Faction ultimate 0653.
"""
from __future__ import annotations

ID = "faction_ultimate_0653"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 653, "tier": 653 % 5}

def apply(context: str = "") -> dict:
    if not context and 653 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
