"""Biome max 0226.
"""
from __future__ import annotations

ID = "biome_max_0226"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 226, "tier": 226 % 5}

def apply(context: str = "") -> dict:
    if not context and 226 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
