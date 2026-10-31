"""Faction peak 0384.
"""
from __future__ import annotations

ID = "faction_peak_0384"

def describe() -> dict:
    return {"id": ID, "kind": "faction", "index": 384, "tier": 384 % 5}

def apply(context: str = "") -> dict:
    if not context and 384 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
