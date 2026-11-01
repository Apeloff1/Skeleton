"""Faction supreme 0462.
"""
from __future__ import annotations

ID = "faction_supreme_0462"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 462, "tier": 462 % 5}

def apply(context: str = "") -> dict:
    if not context and 462 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
