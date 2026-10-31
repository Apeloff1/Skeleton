"""Biome max 0128.
"""
from __future__ import annotations

ID = "biome_max_0128"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 128, "tier": 128 % 5}

def apply(context: str = "") -> dict:
    if not context and 128 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
