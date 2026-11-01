"""Biome ultimate 0687.
"""
from __future__ import annotations

ID = "biome_ultimate_0687"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 687, "tier": 687 % 5}

def apply(context: str = "") -> dict:
    if not context and 687 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
