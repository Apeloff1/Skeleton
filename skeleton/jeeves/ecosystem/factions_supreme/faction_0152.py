"""Faction supreme 0152.
"""
from __future__ import annotations

ID = "faction_supreme_0152"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 152, "tier": 152 % 5}

def apply(context: str = "") -> dict:
    if not context and 152 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
