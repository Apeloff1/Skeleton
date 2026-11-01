"""Biome ultimate 0754.
"""
from __future__ import annotations

ID = "biome_ultimate_0754"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 754, "tier": 754 % 5}

def apply(context: str = "") -> dict:
    if not context and 754 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
