"""Faction max 0293.
"""
from __future__ import annotations

ID = "faction_max_0293"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 293, "tier": 293 % 5}

def apply(context: str = "") -> dict:
    if not context and 293 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
