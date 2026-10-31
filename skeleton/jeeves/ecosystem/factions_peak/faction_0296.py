"""Faction peak 0296.
"""
from __future__ import annotations

ID = "faction_peak_0296"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 296, "tier": 296 % 5}

def apply(context: str = "") -> dict:
    if not context and 296 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
