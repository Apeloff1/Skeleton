"""Faction supreme 0007.
"""
from __future__ import annotations

ID = "faction_supreme_0007"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 7, "tier": 7 % 5}

def apply(context: str = "") -> dict:
    if not context and 7 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
