"""Biome scale 0021.
"""
from __future__ import annotations

ID = "biome_scale_0021"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 21, "tier": 21 % 5}

def apply(context: str = "") -> dict:
    if not context and 21 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
