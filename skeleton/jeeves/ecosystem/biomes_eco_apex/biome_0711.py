"""Biome eco_apex 0711.
"""
from __future__ import annotations

ID = "biome_eco_apex_0711"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 711, "tier": 711 % 5}

def apply(context: str = "") -> dict:
    if not context and 711 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
