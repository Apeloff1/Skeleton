"""Faction ultimate 0408.
"""
from __future__ import annotations

ID = "faction_ultimate_0408"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 408, "tier": 408 % 5}

def apply(context: str = "") -> dict:
    if not context and 408 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
