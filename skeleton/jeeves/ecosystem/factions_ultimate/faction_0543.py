"""Faction ultimate 0543.
"""
from __future__ import annotations

ID = "faction_ultimate_0543"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 543, "tier": 543 % 5}

def apply(context: str = "") -> dict:
    if not context and 543 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
