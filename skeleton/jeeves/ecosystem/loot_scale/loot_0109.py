"""Loot scale 0109.
"""
from __future__ import annotations

ID = "loot_scale_0109"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 109}

def activate(context: str = "") -> dict:
    if not context and 109 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
