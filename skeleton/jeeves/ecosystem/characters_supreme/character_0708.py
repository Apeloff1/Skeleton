"""Character supreme 0708.
"""
from __future__ import annotations

ID = "character_supreme_0708"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 708, "tier": 708 % 5}

def apply(context: str = "") -> dict:
    if not context and 708 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
