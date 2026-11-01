"""Faction supreme 0652.
"""
from __future__ import annotations

ID = "faction_supreme_0652"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 652, "tier": 652 % 5}

def apply(context: str = "") -> dict:
    if not context and 652 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
