"""Biome ultimate 0591.
"""
from __future__ import annotations

ID = "biome_ultimate_0591"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 591, "tier": 591 % 5}

def apply(context: str = "") -> dict:
    if not context and 591 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
