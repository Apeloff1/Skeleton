"""Biome scale 0196.
"""
from __future__ import annotations

ID = "biome_scale_0196"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 196, "tier": 196 % 5}

def apply(context: str = "") -> dict:
    if not context and 196 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
