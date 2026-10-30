"""Biome scale 0009.
"""
from __future__ import annotations

ID = "biome_scale_0009"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 9, "tier": 9 % 5}

def apply(context: str = "") -> dict:
    if not context and 9 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
