"""Biome eco_apex 0620.
"""
from __future__ import annotations

ID = "biome_eco_apex_0620"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 620, "tier": 620 % 5}

def apply(context: str = "") -> dict:
    if not context and 620 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
