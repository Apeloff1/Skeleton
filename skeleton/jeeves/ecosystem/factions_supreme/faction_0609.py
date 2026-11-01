"""Faction supreme 0609.
"""
from __future__ import annotations

ID = "faction_supreme_0609"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 609, "tier": 609 % 5}

def apply(context: str = "") -> dict:
    if not context and 609 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
