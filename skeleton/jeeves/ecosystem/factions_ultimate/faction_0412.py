"""Faction ultimate 0412.
"""
from __future__ import annotations

ID = "faction_ultimate_0412"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 412, "tier": 412 % 5}

def apply(context: str = "") -> dict:
    if not context and 412 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
