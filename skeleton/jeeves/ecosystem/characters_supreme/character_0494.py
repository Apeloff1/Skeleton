"""Character supreme 0494.
"""
from __future__ import annotations

ID = "character_supreme_0494"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 494, "tier": 494 % 5}

def apply(context: str = "") -> dict:
    if not context and 494 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
