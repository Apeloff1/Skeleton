"""Character mega 0296.
"""
from __future__ import annotations

ID = "character_mega_0296"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 296, "tier": 296 % 5}

def apply(context: str = "") -> dict:
    if not context and 296 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
