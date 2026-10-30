"""Raid scale 0003.
"""
from __future__ import annotations

ID = "raid_scale_0003"

def describe() -> dict:
    return {"id": ID, "kind": "raid", "index": 3}

def activate(context: str = "") -> dict:
    if not context and 3 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
