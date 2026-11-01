"""Character supreme 0458.
"""
from __future__ import annotations

ID = "character_supreme_0458"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 458, "tier": 458 % 5}

def apply(context: str = "") -> dict:
    if not context and 458 % 41 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
