"""Biome max 0113.
"""
from __future__ import annotations

ID = "biome_max_0113"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 113, "tier": 113 % 5}

def apply(context: str = "") -> dict:
    if not context and 113 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
