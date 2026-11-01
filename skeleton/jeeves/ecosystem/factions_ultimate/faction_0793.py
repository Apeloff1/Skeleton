"""Faction ultimate 0793.
"""
from __future__ import annotations

ID = "faction_ultimate_0793"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 793, "tier": 793 % 5}

def apply(context: str = "") -> dict:
    if not context and 793 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
