"""Biome eco_apex 0286.
"""
from __future__ import annotations

ID = "biome_eco_apex_0286"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 286, "tier": 286 % 5}

def apply(context: str = "") -> dict:
    if not context and 286 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
