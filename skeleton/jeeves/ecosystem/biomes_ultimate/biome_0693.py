"""Biome ultimate 0693.
"""
from __future__ import annotations

ID = "biome_ultimate_0693"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 693, "tier": 693 % 5}

def apply(context: str = "") -> dict:
    if not context and 693 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
