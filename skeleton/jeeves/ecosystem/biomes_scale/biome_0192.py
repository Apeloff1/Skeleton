"""Biome scale 0192.
"""
from __future__ import annotations

ID = "biome_scale_0192"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 192, "tier": 192 % 5}

def apply(context: str = "") -> dict:
    if not context and 192 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
