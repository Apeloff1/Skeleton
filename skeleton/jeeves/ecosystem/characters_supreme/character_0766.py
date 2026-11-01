"""Character supreme 0766.
"""
from __future__ import annotations

ID = "character_supreme_0766"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 766, "tier": 766 % 5}

def apply(context: str = "") -> dict:
    if not context and 766 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
