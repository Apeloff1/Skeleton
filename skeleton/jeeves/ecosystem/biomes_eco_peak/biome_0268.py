"""Biome eco_peak 0268.
"""
from __future__ import annotations

ID = "biome_eco_peak_0268"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 268, "tier": 268 % 5}

def apply(context: str = "") -> dict:
    if not context and 268 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
