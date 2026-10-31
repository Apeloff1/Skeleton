"""Faction peak 0333.
"""
from __future__ import annotations

ID = "faction_peak_0333"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 333, "tier": 333 % 5}

def apply(context: str = "") -> dict:
    if not context and 333 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
