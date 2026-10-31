"""Biome ultra 0116.
"""
from __future__ import annotations

ID = "biome_ultra_0116"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 116, "tier": 116 % 5}

def apply(context: str = "") -> dict:
    if not context and 116 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
