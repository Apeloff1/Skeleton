"""Biome max 0145.
"""
from __future__ import annotations

ID = "biome_max_0145"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 145, "tier": 145 % 5}

def apply(context: str = "") -> dict:
    if not context and 145 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
