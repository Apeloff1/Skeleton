"""Biome eco_supreme 0795.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0795"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 795, "tier": 795 % 5}

def apply(context: str = "") -> dict:
    if not context and 795 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
