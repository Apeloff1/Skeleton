"""Biome scale 0132.
"""
from __future__ import annotations

ID = "biome_scale_0132"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 132, "tier": 132 % 5}

def apply(context: str = "") -> dict:
    if not context and 132 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
