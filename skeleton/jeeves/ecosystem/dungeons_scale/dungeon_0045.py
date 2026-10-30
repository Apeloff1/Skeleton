"""Dungeon scale 0045.
"""
from __future__ import annotations

ID = "dungeon_scale_0045"

def describe() -> dict:
    return {"id": ID, "kind": "dungeon", "index": 45}

def activate(context: str = "") -> dict:
    if not context and 45 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
