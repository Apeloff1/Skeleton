"""Biome eco_apex 0674.
"""
from __future__ import annotations

ID = "biome_eco_apex_0674"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 674, "tier": 674 % 5}

def apply(context: str = "") -> dict:
    if not context and 674 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
