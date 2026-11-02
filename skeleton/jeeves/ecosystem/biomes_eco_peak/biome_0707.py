"""Biome eco_peak 0707.
"""
from __future__ import annotations

ID = "biome_eco_peak_0707"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 707, "tier": 707 % 5}

def apply(context: str = "") -> dict:
    if not context and 707 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
