"""Character ultra 0141.
"""
from __future__ import annotations

ID = "character_ultra_0141"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 141, "tier": 141 % 5}

def apply(context: str = "") -> dict:
    if not context and 141 % 17 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
