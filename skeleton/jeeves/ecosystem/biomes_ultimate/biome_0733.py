"""Biome ultimate 0733.
"""
from __future__ import annotations

ID = "biome_ultimate_0733"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 733, "tier": 733 % 5}

def apply(context: str = "") -> dict:
    if not context and 733 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
