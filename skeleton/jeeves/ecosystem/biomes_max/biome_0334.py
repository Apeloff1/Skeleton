"""Biome max 0334.
"""
from __future__ import annotations

ID = "biome_max_0334"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 334, "tier": 334 % 5}

def apply(context: str = "") -> dict:
    if not context and 334 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
