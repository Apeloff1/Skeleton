"""Biome scale 0043.
"""
from __future__ import annotations

ID = "biome_scale_0043"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 43, "tier": 43 % 5}

def apply(context: str = "") -> dict:
    if not context and 43 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
