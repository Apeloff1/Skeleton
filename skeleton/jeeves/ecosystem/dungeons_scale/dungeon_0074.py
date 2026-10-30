"""Dungeon scale 0074.
"""
from __future__ import annotations

ID = "dungeon_scale_0074"

def describe() -> dict:
    return {"id": ID, "kind": "dungeon", "index": 74}

def activate(context: str = "") -> dict:
    if not context and 74 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
