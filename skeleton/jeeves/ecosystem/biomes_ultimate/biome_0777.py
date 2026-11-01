"""Biome ultimate 0777.
"""
from __future__ import annotations

ID = "biome_ultimate_0777"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 777, "tier": 777 % 5}

def apply(context: str = "") -> dict:
    if not context and 777 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
