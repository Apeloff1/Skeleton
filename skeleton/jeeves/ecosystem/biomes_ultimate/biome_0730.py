"""Biome ultimate 0730.
"""
from __future__ import annotations

ID = "biome_ultimate_0730"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 730, "tier": 730 % 5}

def apply(context: str = "") -> dict:
    if not context and 730 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
