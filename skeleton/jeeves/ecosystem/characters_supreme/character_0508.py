"""Character supreme 0508.
"""
from __future__ import annotations

ID = "character_supreme_0508"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 508, "tier": 508 % 5}

def apply(context: str = "") -> dict:
    if not context and 508 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
