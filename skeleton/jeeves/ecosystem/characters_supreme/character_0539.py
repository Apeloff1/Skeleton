"""Character supreme 0539.
"""
from __future__ import annotations

ID = "character_supreme_0539"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 539, "tier": 539 % 5}

def apply(context: str = "") -> dict:
    if not context and 539 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
