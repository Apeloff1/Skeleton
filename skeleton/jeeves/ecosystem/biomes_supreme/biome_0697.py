"""Biome supreme 0697.
"""
from __future__ import annotations

ID = "biome_supreme_0697"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 697, "tier": 697 % 5}

def apply(context: str = "") -> dict:
    if not context and 697 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
