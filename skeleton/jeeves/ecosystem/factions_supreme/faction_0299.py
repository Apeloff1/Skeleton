"""Faction supreme 0299.
"""
from __future__ import annotations

ID = "faction_supreme_0299"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 299, "tier": 299 % 5}

def apply(context: str = "") -> dict:
    if not context and 299 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
