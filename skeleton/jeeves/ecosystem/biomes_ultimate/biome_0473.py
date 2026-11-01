"""Biome ultimate 0473.
"""
from __future__ import annotations

ID = "biome_ultimate_0473"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 473, "tier": 473 % 5}

def apply(context: str = "") -> dict:
    if not context and 473 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
