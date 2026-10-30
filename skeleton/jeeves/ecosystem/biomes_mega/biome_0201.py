"""Biome mega 0201.
"""
from __future__ import annotations

ID = "biome_mega_0201"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 201, "tier": 201 % 5}

def apply(context: str = "") -> dict:
    if not context and 201 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
