"""Loot scale 0099.
"""
from __future__ import annotations

ID = "loot_scale_0099"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 99}

def activate(context: str = "") -> dict:
    if not context and 99 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
