"""Faction ultra_max 0500.
"""
from __future__ import annotations

ID = "faction_ultra_max_0500"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 500, "tier": 500 % 5}

def apply(context: str = "") -> dict:
    if not context and 500 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
