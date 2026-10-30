"""Character mega 0257.
"""
from __future__ import annotations

ID = "character_mega_0257"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 257, "tier": 257 % 5}

def apply(context: str = "") -> dict:
    if not context and 257 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
