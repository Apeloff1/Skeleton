"""Faction ultra 0210.
"""
from __future__ import annotations

ID = "faction_ultra_0210"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 210, "tier": 210 % 5}

def apply(context: str = "") -> dict:
    if not context and 210 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
