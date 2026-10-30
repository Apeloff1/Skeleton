"""Loot scale 0082.
"""
from __future__ import annotations

ID = "loot_scale_0082"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 82}

def activate(context: str = "") -> dict:
    if not context and 82 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
