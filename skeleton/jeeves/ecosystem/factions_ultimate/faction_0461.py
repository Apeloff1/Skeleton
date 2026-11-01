"""Faction ultimate 0461.
"""
from __future__ import annotations

ID = "faction_ultimate_0461"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 461, "tier": 461 % 5}

def apply(context: str = "") -> dict:
    if not context and 461 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
