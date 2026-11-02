"""Biome eco_supreme 0738.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0738"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 738, "tier": 738 % 5}

def apply(context: str = "") -> dict:
    if not context and 738 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
