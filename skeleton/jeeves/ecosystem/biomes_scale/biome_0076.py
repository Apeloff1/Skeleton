"""Biome scale 0076.
"""
from __future__ import annotations

ID = "biome_scale_0076"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 76, "tier": 76 % 5}

def apply(context: str = "") -> dict:
    if not context and 76 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
