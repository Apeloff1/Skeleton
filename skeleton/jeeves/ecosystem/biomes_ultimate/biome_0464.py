"""Biome ultimate 0464.
"""
from __future__ import annotations

ID = "biome_ultimate_0464"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 464, "tier": 464 % 5}

def apply(context: str = "") -> dict:
    if not context and 464 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
