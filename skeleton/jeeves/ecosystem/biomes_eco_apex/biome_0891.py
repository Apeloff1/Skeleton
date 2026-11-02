"""Biome eco_apex 0891.
"""
from __future__ import annotations

ID = "biome_eco_apex_0891"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 891, "tier": 891 % 5}

def apply(context: str = "") -> dict:
    if not context and 891 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
