"""Character mega 0276.
"""
from __future__ import annotations

ID = "character_mega_0276"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 276, "tier": 276 % 5}

def apply(context: str = "") -> dict:
    if not context and 276 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
