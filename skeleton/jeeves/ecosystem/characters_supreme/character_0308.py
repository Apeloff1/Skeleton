"""Character supreme 0308.
"""
from __future__ import annotations

ID = "character_supreme_0308"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 308, "tier": 308 % 5}

def apply(context: str = "") -> dict:
    if not context and 308 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
