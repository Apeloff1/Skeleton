"""Biome mega 0188.
"""
from __future__ import annotations

ID = "biome_mega_0188"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 188, "tier": 188 % 5}

def apply(context: str = "") -> dict:
    if not context and 188 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
