"""Faction supreme 0638.
"""
from __future__ import annotations

ID = "faction_supreme_0638"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 638, "tier": 638 % 5}

def apply(context: str = "") -> dict:
    if not context and 638 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
