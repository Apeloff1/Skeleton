"""Biome scale 0050.
"""
from __future__ import annotations

ID = "biome_scale_0050"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 50, "tier": 50 % 5}

def apply(context: str = "") -> dict:
    if not context and 50 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
