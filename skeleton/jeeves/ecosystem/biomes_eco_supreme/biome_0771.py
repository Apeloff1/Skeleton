"""Biome eco_supreme 0771.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0771"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 771, "tier": 771 % 5}

def apply(context: str = "") -> dict:
    if not context and 771 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
