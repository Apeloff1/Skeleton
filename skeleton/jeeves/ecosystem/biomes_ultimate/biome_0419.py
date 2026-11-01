"""Biome ultimate 0419.
"""
from __future__ import annotations

ID = "biome_ultimate_0419"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 419, "tier": 419 % 5}

def apply(context: str = "") -> dict:
    if not context and 419 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
