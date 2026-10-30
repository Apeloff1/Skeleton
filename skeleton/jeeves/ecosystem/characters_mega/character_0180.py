"""Character mega 0180.
"""
from __future__ import annotations

ID = "character_mega_0180"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 180, "tier": 180 % 5}

def apply(context: str = "") -> dict:
    if not context and 180 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
