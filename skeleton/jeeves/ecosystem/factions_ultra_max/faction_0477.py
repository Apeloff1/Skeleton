"""Faction ultra_max 0477.
"""
from __future__ import annotations

ID = "faction_ultra_max_0477"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 477, "tier": 477 % 5}

def apply(context: str = "") -> dict:
    if not context and 477 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
