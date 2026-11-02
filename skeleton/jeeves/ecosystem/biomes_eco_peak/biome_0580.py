"""Biome eco_peak 0580.
"""
from __future__ import annotations

ID = "biome_eco_peak_0580"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 580, "tier": 580 % 5}

def apply(context: str = "") -> dict:
    if not context and 580 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
