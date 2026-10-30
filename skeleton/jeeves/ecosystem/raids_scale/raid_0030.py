"""Raid scale 0030.
"""
from __future__ import annotations

ID = "raid_scale_0030"

def describe() -> dict:
    return {"id": ID, "kind": "raid", "index": 30}

def activate(context: str = "") -> dict:
    if not context and 30 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
