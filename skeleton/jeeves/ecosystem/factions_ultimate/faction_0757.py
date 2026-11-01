"""Faction ultimate 0757.
"""
from __future__ import annotations

ID = "faction_ultimate_0757"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 757, "tier": 757 % 5}

def apply(context: str = "") -> dict:
    if not context and 757 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
