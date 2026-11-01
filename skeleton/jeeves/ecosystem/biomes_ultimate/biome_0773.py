"""Biome ultimate 0773.
"""
from __future__ import annotations

ID = "biome_ultimate_0773"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 773, "tier": 773 % 5}

def apply(context: str = "") -> dict:
    if not context and 773 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
