"""Loot scale 0018.
"""
from __future__ import annotations

ID = "loot_scale_0018"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 18}

def activate(context: str = "") -> dict:
    if not context and 18 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
