"""Biome eco_supreme 0890.
"""
from __future__ import annotations

ID = "biome_eco_supreme_0890"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 890, "tier": 890 % 5}

def apply(context: str = "") -> dict:
    if not context and 890 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
