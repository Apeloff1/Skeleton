"""Faction ultra 0150.
"""
from __future__ import annotations

ID = "faction_ultra_0150"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 150, "tier": 150 % 5}

def apply(context: str = "") -> dict:
    if not context and 150 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
