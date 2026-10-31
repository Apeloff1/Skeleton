"""Faction peak 0377.
"""
from __future__ import annotations

ID = "faction_peak_0377"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 377, "tier": 377 % 5}

def apply(context: str = "") -> dict:
    if not context and 377 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
