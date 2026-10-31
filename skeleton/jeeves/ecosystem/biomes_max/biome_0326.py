"""Biome max 0326.
"""
from __future__ import annotations

ID = "biome_max_0326"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 326, "tier": 326 % 5}

def apply(context: str = "") -> dict:
    if not context and 326 % 19 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
