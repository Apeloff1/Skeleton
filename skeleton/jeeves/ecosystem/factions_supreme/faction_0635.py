"""Faction supreme 0635.
"""
from __future__ import annotations

ID = "faction_supreme_0635"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 635, "tier": 635 % 5}

def apply(context: str = "") -> dict:
    if not context and 635 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
