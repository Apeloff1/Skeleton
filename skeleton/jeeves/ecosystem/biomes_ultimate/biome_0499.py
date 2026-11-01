"""Biome ultimate 0499.
"""
from __future__ import annotations

ID = "biome_ultimate_0499"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 499, "tier": 499 % 5}

def apply(context: str = "") -> dict:
    if not context and 499 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
