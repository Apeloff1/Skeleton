"""Character mega 0226.
"""
from __future__ import annotations

ID = "character_mega_0226"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 226, "tier": 226 % 5}

def apply(context: str = "") -> dict:
    if not context and 226 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
