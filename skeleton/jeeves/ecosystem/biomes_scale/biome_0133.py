"""Biome scale 0133.
"""
from __future__ import annotations

ID = "biome_scale_0133"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 133, "tier": 133 % 5}

def apply(context: str = "") -> dict:
    if not context and 133 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
