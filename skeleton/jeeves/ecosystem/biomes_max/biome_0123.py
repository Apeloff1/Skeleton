"""Biome max 0123.
"""
from __future__ import annotations

ID = "biome_max_0123"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 123, "tier": 123 % 5}

def apply(context: str = "") -> dict:
    if not context and 123 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
