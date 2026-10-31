"""Faction max 0344.
"""
from __future__ import annotations

ID = "faction_max_0344"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 344, "tier": 344 % 5}

def apply(context: str = "") -> dict:
    if not context and 344 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
