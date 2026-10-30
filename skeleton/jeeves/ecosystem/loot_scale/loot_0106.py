"""Loot scale 0106.
"""
from __future__ import annotations

ID = "loot_scale_0106"

def describe() -> dict:
    return {"id": ID, "kind": "loot", "index": 106}

def activate(context: str = "") -> dict:
    if not context and 106 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
