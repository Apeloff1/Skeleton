"""Biome mega 0061.
"""
from __future__ import annotations

ID = "biome_mega_0061"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 61, "tier": 61 % 5}

def apply(context: str = "") -> dict:
    if not context and 61 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
