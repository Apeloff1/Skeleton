"""Faction ultimate 0546.
"""
from __future__ import annotations

ID = "faction_ultimate_0546"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 546, "tier": 546 % 5}

def apply(context: str = "") -> dict:
    if not context and 546 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
