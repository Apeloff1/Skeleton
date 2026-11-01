"""Biome ultimate 0577.
"""
from __future__ import annotations

ID = "biome_ultimate_0577"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 577, "tier": 577 % 5}

def apply(context: str = "") -> dict:
    if not context and 577 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
