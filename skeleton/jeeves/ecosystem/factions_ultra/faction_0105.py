"""Faction ultra 0105.
"""
from __future__ import annotations

ID = "faction_ultra_0105"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 105, "tier": 105 % 5}

def apply(context: str = "") -> dict:
    if not context and 105 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
