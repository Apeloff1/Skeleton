"""Biome ultimate 0613.
"""
from __future__ import annotations

ID = "biome_ultimate_0613"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 613, "tier": 613 % 5}

def apply(context: str = "") -> dict:
    if not context and 613 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
