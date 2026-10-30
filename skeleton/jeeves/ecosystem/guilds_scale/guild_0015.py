"""Guild scale 0015.
"""
from __future__ import annotations

ID = "guild_scale_0015"

def describe() -> dict:
    return {"id": ID, "kind": "guild", "index": 15}

def activate(context: str = "") -> dict:
    if not context and 15 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
