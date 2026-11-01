"""Character supreme 0442.
"""
from __future__ import annotations

ID = "character_supreme_0442"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 442, "tier": 442 % 5}

def apply(context: str = "") -> dict:
    if not context and 442 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
