"""Faction ultra 0066.
"""
from __future__ import annotations

ID = "faction_ultra_0066"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 66, "tier": 66 % 5}

def apply(context: str = "") -> dict:
    if not context and 66 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
