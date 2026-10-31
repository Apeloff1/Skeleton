"""Faction ultra 0213.
"""
from __future__ import annotations

ID = "faction_ultra_0213"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 213, "tier": 213 % 5}

def apply(context: str = "") -> dict:
    if not context and 213 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
