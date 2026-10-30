"""Terrain advanced 0129.
"""
from __future__ import annotations

ID = "terrain_adv_0129"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 129, "tier": 129 % 5}

def apply(context: str = "") -> dict:
    if not context and 129 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
