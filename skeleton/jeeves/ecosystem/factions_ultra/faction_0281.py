"""Faction ultra 0281.
"""
from __future__ import annotations

ID = "faction_ultra_0281"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 281, "tier": 281 % 5}

def apply(context: str = "") -> dict:
    if not context and 281 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
