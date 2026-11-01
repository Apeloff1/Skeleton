"""Biome ultimate 0782.
"""
from __future__ import annotations

ID = "biome_ultimate_0782"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 782, "tier": 782 % 5}

def apply(context: str = "") -> dict:
    if not context and 782 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
