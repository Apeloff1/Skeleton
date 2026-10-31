"""Biome ultra 0127.
"""
from __future__ import annotations

ID = "biome_ultra_0127"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 127, "tier": 127 % 5}

def apply(context: str = "") -> dict:
    if not context and 127 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
