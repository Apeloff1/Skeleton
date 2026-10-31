"""Faction peak 0351.
"""
from __future__ import annotations

ID = "faction_peak_0351"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 351, "tier": 351 % 5}

def apply(context: str = "") -> dict:
    if not context and 351 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
