"""Biome max 0275.
"""
from __future__ import annotations

ID = "biome_max_0275"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 275, "tier": 275 % 5}

def apply(context: str = "") -> dict:
    if not context and 275 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
