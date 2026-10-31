"""Faction peak 0369.
"""
from __future__ import annotations

ID = "faction_peak_0369"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 369, "tier": 369 % 5}

def apply(context: str = "") -> dict:
    if not context and 369 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
