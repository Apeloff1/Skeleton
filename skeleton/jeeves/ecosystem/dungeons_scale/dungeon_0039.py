"""Dungeon scale 0039.
"""
from __future__ import annotations

ID = "dungeon_scale_0039"

def describe() -> dict:
    return {"id": ID, "kind": "dungeon", "index": 39}

def activate(context: str = "") -> dict:
    if not context and 39 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
