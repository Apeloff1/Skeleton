"""Biome ultimate 0639.
"""
from __future__ import annotations

ID = "biome_ultimate_0639"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 639, "tier": 639 % 5}

def apply(context: str = "") -> dict:
    if not context and 639 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
