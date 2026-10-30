"""Character mega 0263.
"""
from __future__ import annotations

ID = "character_mega_0263"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 263, "tier": 263 % 5}

def apply(context: str = "") -> dict:
    if not context and 263 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
