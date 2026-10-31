"""Biome max 0006.
"""
from __future__ import annotations

ID = "biome_max_0006"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 6, "tier": 6 % 5}

def apply(context: str = "") -> dict:
    if not context and 6 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
