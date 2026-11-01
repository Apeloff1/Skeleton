"""Biome ultimate 0564.
"""
from __future__ import annotations

ID = "biome_ultimate_0564"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 564, "tier": 564 % 5}

def apply(context: str = "") -> dict:
    if not context and 564 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
