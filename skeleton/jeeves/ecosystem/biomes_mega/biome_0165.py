"""Biome mega 0165.
"""
from __future__ import annotations

ID = "biome_mega_0165"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 165, "tier": 165 % 5}

def apply(context: str = "") -> dict:
    if not context and 165 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
