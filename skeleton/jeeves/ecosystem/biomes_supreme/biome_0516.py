"""Biome supreme 0516.
"""
from __future__ import annotations

ID = "biome_supreme_0516"

def describe() -> dict:
    return {"id": ID, "kind": "biome", "index": 516, "tier": 516 % 5}

def apply(context: str = "") -> dict:
    if not context and 516 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
