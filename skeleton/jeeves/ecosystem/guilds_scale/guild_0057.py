"""Guild scale 0057.
"""
from __future__ import annotations

ID = "guild_scale_0057"

def describe() -> dict:
    return {"id": ID, "kind": "guild", "index": 57}

def activate(context: str = "") -> dict:
    if not context and 57 % 7 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:120], "active": True}
