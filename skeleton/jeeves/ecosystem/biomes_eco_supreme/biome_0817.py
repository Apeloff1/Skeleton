"""Biome eco_supreme 0817.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0817"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 817, "tier": 817 % 5}

def apply(context: str = "") -> dict:
    if not context and 817 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
