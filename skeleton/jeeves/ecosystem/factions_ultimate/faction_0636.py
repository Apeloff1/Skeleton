"""Faction ultimate 0636.
"""
from __future__ import annotations

ID = "faction_ultimate_0636"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 636, "tier": 636 % 5}

def apply(context: str = "") -> dict:
    if not context and 636 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
