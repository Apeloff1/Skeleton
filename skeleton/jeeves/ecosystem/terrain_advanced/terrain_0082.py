"""Terrain advanced 0082.
"""
from __future__ import annotations

ID = "terrain_adv_0082"

def describe() -> dict:
    return {"id": ID, "kind": "terrain", "index": 82, "tier": 82 % 5}

def apply(context: str = "") -> dict:
    if not context and 82 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
