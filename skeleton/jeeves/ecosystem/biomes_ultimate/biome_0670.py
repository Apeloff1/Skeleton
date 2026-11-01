"""Biome ultimate 0670.
"""
from __future__ import annotations

ID = "biome_ultimate_0670"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 670, "tier": 670 % 5}

def apply(context: str = "") -> dict:
    if not context and 670 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
