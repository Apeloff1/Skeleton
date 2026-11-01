"""Biome supreme 0543.
"""
from __future__ import annotations

ID = "biome_supreme_0543"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 543, "tier": 543 % 5}

def apply(context: str = "") -> dict:
    if not context and 543 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
