"""Biome eco_supreme 0772.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0772"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 772, "tier": 772 % 5}

def apply(context: str = "") -> dict:
    if not context and 772 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
