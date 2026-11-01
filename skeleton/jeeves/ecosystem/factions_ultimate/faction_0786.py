"""Faction ultimate 0786.
"""
from __future__ import annotations

ID = "faction_ultimate_0786"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 786, "tier": 786 % 5}

def apply(context: str = "") -> dict:
    if not context and 786 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
