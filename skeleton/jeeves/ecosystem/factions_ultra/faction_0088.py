"""Faction ultra 0088.
"""
from __future__ import annotations

ID = "faction_ultra_0088"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 88, "tier": 88 % 5}

def apply(context: str = "") -> dict:
    if not context and 88 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
