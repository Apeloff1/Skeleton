"""Biome max 0332.
"""
from __future__ import annotations

ID = "biome_max_0332"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 332, "tier": 332 % 5}

def apply(context: str = "") -> dict:
    if not context and 332 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
