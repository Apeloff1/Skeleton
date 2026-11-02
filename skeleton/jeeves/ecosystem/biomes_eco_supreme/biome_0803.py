"""Biome eco_supreme 0803.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0803"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 803, "tier": 803 % 5}

def apply(context: str = "") -> dict:
    if not context and 803 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
