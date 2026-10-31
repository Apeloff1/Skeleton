"""Faction max 0331.
"""
from __future__ import annotations

ID = "faction_max_0331"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 331, "tier": 331 % 5}

def apply(context: str = "") -> dict:
    if not context and 331 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
