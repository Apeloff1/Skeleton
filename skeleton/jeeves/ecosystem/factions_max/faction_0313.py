"""Faction max 0313.
"""
from __future__ import annotations

ID = "faction_max_0313"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 313, "tier": 313 % 5}

def apply(context: str = "") -> dict:
    if not context and 313 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
