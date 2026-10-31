"""Faction peak 0397.
"""
from __future__ import annotations

ID = "faction_peak_0397"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 397, "tier": 397 % 5}

def apply(context: str = "") -> dict:
    if not context and 397 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
