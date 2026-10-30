"""Biome mega 0189.
"""
from __future__ import annotations

ID = "biome_mega_0189"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 189, "tier": 189 % 5}

def apply(context: str = "") -> dict:
    if not context and 189 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
