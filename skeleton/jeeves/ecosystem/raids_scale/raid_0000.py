"""Raid scale 0000.
"""
from __future__ import annotations

ID = "raid_scale_0000"

def describe() -> dict:
    return {"id": ID, "kind": "raid", "index": 0}

def activate(context: str = "") -> dict:
    if not context and 0 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
