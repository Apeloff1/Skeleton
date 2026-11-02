"""Biome eco_supreme 0820.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0820"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 820, "tier": 820 % 5}

def apply(context: str = "") -> dict:
    if not context and 820 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
