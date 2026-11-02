"""Biome eco_apex 0400.
"""
from __future__ import annotations

ID = "biome_eco_apex_0400"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 400, "tier": 400 % 5}

def apply(context: str = "") -> dict:
    if not context and 400 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
