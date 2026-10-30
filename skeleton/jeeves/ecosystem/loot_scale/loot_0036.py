"""Loot scale 0036.
"""
from __future__ import annotations

ID = "loot_scale_0036"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 36}

def activate(context: str = "") -> dict:
    if not context and 36 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
