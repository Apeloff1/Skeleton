"""Biome max 0282.
"""
from __future__ import annotations

ID = "biome_max_0282"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 282, "tier": 282 % 5}

def apply(context: str = "") -> dict:
    if not context and 282 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
