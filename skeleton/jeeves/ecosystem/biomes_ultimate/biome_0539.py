"""Biome ultimate 0539.
"""
from __future__ import annotations

ID = "biome_ultimate_0539"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 539, "tier": 539 % 5}

def apply(context: str = "") -> dict:
    if not context and 539 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
