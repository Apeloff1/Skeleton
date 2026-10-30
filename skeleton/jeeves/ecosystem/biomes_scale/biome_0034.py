"""Biome scale 0034.
"""
from __future__ import annotations

ID = "biome_scale_0034"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 34, "tier": 34 % 5}

def apply(context: str = "") -> dict:
    if not context and 34 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
