"""Biome ultimate 0797.
"""
from __future__ import annotations

ID = "biome_ultimate_0797"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 797, "tier": 797 % 5}

def apply(context: str = "") -> dict:
    if not context and 797 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
