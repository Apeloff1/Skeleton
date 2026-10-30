"""Biome scale 0179.
"""
from __future__ import annotations

ID = "biome_scale_0179"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 179, "tier": 179 % 5}

def apply(context: str = "") -> dict:
    if not context and 179 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
