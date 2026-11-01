"""Biome ultimate 0387.
"""
from __future__ import annotations

ID = "biome_ultimate_0387"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 387, "tier": 387 % 5}

def apply(context: str = "") -> dict:
    if not context and 387 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
