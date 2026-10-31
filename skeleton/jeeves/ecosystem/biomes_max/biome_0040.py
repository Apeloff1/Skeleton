"""Biome max 0040.
"""
from __future__ import annotations

ID = "biome_max_0040"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 40, "tier": 40 % 5}

def apply(context: str = "") -> dict:
    if not context and 40 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
