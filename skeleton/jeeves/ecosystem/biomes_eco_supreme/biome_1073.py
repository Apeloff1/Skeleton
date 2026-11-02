"""Biome eco_supreme 1073.
"""
from __future__ import annotations

ID = "biome_eco_supreme_1073"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 1073, "tier": 1073 % 5}

def apply(context: str = "") -> dict:
    if not context and 1073 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
