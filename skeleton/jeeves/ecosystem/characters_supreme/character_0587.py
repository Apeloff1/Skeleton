"""Character supreme 0587.
"""
from __future__ import annotations

ID = "character_supreme_0587"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 587, "tier": 587 % 5}

def apply(context: str = "") -> dict:
    if not context and 587 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
