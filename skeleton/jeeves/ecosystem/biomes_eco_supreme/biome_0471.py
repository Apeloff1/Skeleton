"""Biome eco_supreme 0471.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0471"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 471, "tier": 471 % 5}

def apply(context: str = "") -> dict:
    if not context and 471 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
