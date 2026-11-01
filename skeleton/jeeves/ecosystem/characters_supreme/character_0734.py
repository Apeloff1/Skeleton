"""Character supreme 0734.
"""
from __future__ import annotations

ID = "character_supreme_0734"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 734, "tier": 734 % 5}

def apply(context: str = "") -> dict:
    if not context and 734 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
