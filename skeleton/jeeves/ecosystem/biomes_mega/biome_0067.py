"""Biome mega 0067.
"""
from __future__ import annotations

ID = "biome_mega_0067"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 67, "tier": 67 % 5}

def apply(context: str = "") -> dict:
    if not context and 67 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
