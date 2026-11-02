"""Biome eco_apex 0461.
"""
from __future__ import annotations

ID = "biome_eco_apex_0461"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 461, "tier": 461 % 5}

def apply(context: str = "") -> dict:
    if not context and 461 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
