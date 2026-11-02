"""Biome eco_peak 0301.
"""
from __future__ import annotations

ID = "biome_eco_peak_0301"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 301, "tier": 301 % 5}

def apply(context: str = "") -> dict:
    if not context and 301 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
