"""Faction ultra 0170.
"""
from __future__ import annotations

ID = "faction_ultra_0170"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 170, "tier": 170 % 5}

def apply(context: str = "") -> dict:
    if not context and 170 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
