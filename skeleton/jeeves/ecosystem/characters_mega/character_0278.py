"""Character mega 0278.
"""
from __future__ import annotations

ID = "character_mega_0278"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 278, "tier": 278 % 5}

def apply(context: str = "") -> dict:
    if not context and 278 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
