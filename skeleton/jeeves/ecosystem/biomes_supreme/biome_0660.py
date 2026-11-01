"""Biome supreme 0660.
"""
from __future__ import annotations

ID = "biome_supreme_0660"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 660, "tier": 660 % 5}

def apply(context: str = "") -> dict:
    if not context and 660 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
