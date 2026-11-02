"""Biome eco_supreme 0345.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0345"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 345, "tier": 345 % 5}

def apply(context: str = "") -> dict:
    if not context and 345 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
