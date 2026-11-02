"""Biome eco_supreme 0671.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0671"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 671, "tier": 671 % 5}

def apply(context: str = "") -> dict:
    if not context and 671 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
