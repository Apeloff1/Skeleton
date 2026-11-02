"""Biome eco_peak 0846.
"""
from __future__ import annotations

ID = "biome_eco_peak_0846"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 846, "tier": 846 % 5}

def apply(context: str = "") -> dict:
    if not context and 846 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
