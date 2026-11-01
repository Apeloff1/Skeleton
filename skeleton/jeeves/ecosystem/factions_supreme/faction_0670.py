"""Faction supreme 0670.
"""
from __future__ import annotations

ID = "faction_supreme_0670"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 670, "tier": 670 % 5}

def apply(context: str = "") -> dict:
    if not context and 670 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
