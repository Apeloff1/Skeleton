"""Character mega 0255.
"""
from __future__ import annotations

ID = "character_mega_0255"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 255, "tier": 255 % 5}

def apply(context: str = "") -> dict:
    if not context and 255 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
