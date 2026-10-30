"""Biome mega 0204.
"""
from __future__ import annotations

ID = "biome_mega_0204"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 204, "tier": 204 % 5}

def apply(context: str = "") -> dict:
    if not context and 204 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
