"""Faction ultra 0237.
"""
from __future__ import annotations

ID = "faction_ultra_0237"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 237, "tier": 237 % 5}

def apply(context: str = "") -> dict:
    if not context and 237 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
