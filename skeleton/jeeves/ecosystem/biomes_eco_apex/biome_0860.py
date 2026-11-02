"""Biome eco_apex 0860.
"""
from __future__ import annotations

ID = "biome_eco_apex_0860"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 860, "tier": 860 % 5}

def apply(context: str = "") -> dict:
    if not context and 860 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
