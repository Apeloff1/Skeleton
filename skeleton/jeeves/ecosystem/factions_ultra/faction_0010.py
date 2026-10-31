"""Faction ultra 0010.
"""
from __future__ import annotations

ID = "faction_ultra_0010"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 10, "tier": 10 % 5}

def apply(context: str = "") -> dict:
    if not context and 10 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
