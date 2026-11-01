"""Faction ultimate 0632.
"""
from __future__ import annotations

ID = "faction_ultimate_0632"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 632, "tier": 632 % 5}

def apply(context: str = "") -> dict:
    if not context and 632 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
