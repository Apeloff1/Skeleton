"""Faction ultimate 0656.
"""
from __future__ import annotations

ID = "faction_ultimate_0656"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 656, "tier": 656 % 5}

def apply(context: str = "") -> dict:
    if not context and 656 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
