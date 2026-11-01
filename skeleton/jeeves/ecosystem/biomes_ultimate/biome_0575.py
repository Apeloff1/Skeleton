"""Biome ultimate 0575.
"""
from __future__ import annotations

ID = "biome_ultimate_0575"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 575, "tier": 575 % 5}

def apply(context: str = "") -> dict:
    if not context and 575 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
