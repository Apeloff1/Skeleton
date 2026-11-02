"""Biome eco_peak 0601.
"""
from __future__ import annotations

ID = "biome_eco_peak_0601"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 601, "tier": 601 % 5}

def apply(context: str = "") -> dict:
    if not context and 601 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
