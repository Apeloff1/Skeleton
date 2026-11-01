"""Faction ultimate 0760.
"""
from __future__ import annotations

ID = "faction_ultimate_0760"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 760, "tier": 760 % 5}

def apply(context: str = "") -> dict:
    if not context and 760 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
