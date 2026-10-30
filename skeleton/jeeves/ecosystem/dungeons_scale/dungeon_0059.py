"""Dungeon scale 0059.
"""
from __future__ import annotations

ID = "dungeon_scale_0059"

def describe() -> dict:
    return {"id": ID, "kind": "dungeon", "index": 59}

def activate(context: str = "") -> dict:
    if not context and 59 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
