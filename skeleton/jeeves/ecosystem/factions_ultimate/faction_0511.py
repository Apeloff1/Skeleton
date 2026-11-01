"""Faction ultimate 0511.
"""
from __future__ import annotations

ID = "faction_ultimate_0511"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 511, "tier": 511 % 5}

def apply(context: str = "") -> dict:
    if not context and 511 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
