"""Faction ultimate 0356.
"""
from __future__ import annotations

ID = "faction_ultimate_0356"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 356, "tier": 356 % 5}

def apply(context: str = "") -> dict:
    if not context and 356 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
