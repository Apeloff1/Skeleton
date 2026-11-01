"""Faction ultimate 0691.
"""
from __future__ import annotations

ID = "faction_ultimate_0691"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 691, "tier": 691 % 5}

def apply(context: str = "") -> dict:
    if not context and 691 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
