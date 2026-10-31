"""Faction ultra 0155.
"""
from __future__ import annotations

ID = "faction_ultra_0155"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 155, "tier": 155 % 5}

def apply(context: str = "") -> dict:
    if not context and 155 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
