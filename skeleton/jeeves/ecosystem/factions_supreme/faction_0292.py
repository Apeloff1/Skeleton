"""Faction supreme 0292.
"""
from __future__ import annotations

ID = "faction_supreme_0292"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 292, "tier": 292 % 5}

def apply(context: str = "") -> dict:
    if not context and 292 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
