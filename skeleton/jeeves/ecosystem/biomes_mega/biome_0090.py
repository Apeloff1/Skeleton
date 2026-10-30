"""Biome mega 0090.
"""
from __future__ import annotations

ID = "biome_mega_0090"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 90, "tier": 90 % 5}

def apply(context: str = "") -> dict:
    if not context and 90 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
