"""Faction ultimate 0679.
"""
from __future__ import annotations

ID = "faction_ultimate_0679"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 679, "tier": 679 % 5}

def apply(context: str = "") -> dict:
    if not context and 679 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
