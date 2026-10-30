"""Guild scale 0006.
"""
from __future__ import annotations

ID = "guild_scale_0006"

def describe() -> dict:
    return {"id": ID, "kind": "guild", "index": 6}

def activate(context: str = "") -> dict:
    if not context and 6 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
