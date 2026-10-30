"""Biome mega 0243.
"""
from __future__ import annotations

ID = "biome_mega_0243"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 243, "tier": 243 % 5}

def apply(context: str = "") -> dict:
    if not context and 243 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
