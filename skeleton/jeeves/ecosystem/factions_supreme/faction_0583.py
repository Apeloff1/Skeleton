"""Faction supreme 0583.
"""
from __future__ import annotations

ID = "faction_supreme_0583"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 583, "tier": 583 % 5}

def apply(context: str = "") -> dict:
    if not context and 583 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
