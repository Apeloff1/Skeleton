"""Dungeon scale 0050.
"""
from __future__ import annotations

ID = "dungeon_scale_0050"

def describe() -> dict:
    return {"id": ID, "kind": "dungeon", "index": 50}

def activate(context: str = "") -> dict:
    if not context and 50 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
