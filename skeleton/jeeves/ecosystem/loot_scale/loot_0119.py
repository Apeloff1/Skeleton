"""Loot scale 0119.
"""
from __future__ import annotations

ID = "loot_scale_0119"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 119}

def activate(context: str = "") -> dict:
    if not context and 119 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
