"""Biome scale 0041.
"""
from __future__ import annotations

ID = "biome_scale_0041"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 41, "tier": 41 % 5}

def apply(context: str = "") -> dict:
    if not context and 41 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
