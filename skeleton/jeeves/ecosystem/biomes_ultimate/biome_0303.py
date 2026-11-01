"""Biome ultimate 0303.
"""
from __future__ import annotations

ID = "biome_ultimate_0303"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 303, "tier": 303 % 5}

def apply(context: str = "") -> dict:
    if not context and 303 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
