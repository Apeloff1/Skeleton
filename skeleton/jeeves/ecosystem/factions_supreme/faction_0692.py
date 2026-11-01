"""Faction supreme 0692.
"""
from __future__ import annotations

ID = "faction_supreme_0692"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 692, "tier": 692 % 5}

def apply(context: str = "") -> dict:
    if not context and 692 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
