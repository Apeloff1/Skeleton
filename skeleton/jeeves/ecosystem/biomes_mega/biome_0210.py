"""Biome mega 0210.
"""
from __future__ import annotations

ID = "biome_mega_0210"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 210, "tier": 210 % 5}

def apply(context: str = "") -> dict:
    if not context and 210 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
