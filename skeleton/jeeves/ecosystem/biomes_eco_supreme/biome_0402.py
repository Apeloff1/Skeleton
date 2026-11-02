"""Biome eco_supreme 0402.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0402"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 402, "tier": 402 % 5}

def apply(context: str = "") -> dict:
    if not context and 402 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
