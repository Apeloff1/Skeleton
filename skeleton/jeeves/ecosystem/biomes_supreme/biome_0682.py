"""Biome supreme 0682.
"""
from __future__ import annotations

ID = "biome_supreme_0682"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 682, "tier": 682 % 5}

def apply(context: str = "") -> dict:
    if not context and 682 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
