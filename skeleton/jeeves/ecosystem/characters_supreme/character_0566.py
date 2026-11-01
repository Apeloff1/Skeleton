"""Character supreme 0566.
"""
from __future__ import annotations

ID = "character_supreme_0566"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 566, "tier": 566 % 5}

def apply(context: str = "") -> dict:
    if not context and 566 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
