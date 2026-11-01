"""Character supreme 0748.
"""
from __future__ import annotations

ID = "character_supreme_0748"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 748, "tier": 748 % 5}

def apply(context: str = "") -> dict:
    if not context and 748 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
