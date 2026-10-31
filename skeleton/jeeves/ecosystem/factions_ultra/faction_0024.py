"""Faction ultra 0024.
"""
from __future__ import annotations

ID = "faction_ultra_0024"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 24, "tier": 24 % 5}

def apply(context: str = "") -> dict:
    if not context and 24 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
