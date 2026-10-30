"""Dungeon scale 0017.
"""
from __future__ import annotations

ID = "dungeon_scale_0017"

def describe() -> dict:
    return {"id": ID, "kind": "dungeon", "index": 17}

def activate(context: str = "") -> dict:
    if not context and 17 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
