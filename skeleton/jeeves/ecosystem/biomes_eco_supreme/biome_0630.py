"""Biome eco_supreme 0630.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0630"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 630, "tier": 630 % 5}

def apply(context: str = "") -> dict:
    if not context and 630 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
