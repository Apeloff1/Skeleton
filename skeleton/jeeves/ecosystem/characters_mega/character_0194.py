"""Character mega 0194.
"""
from __future__ import annotations

ID = "character_mega_0194"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 194, "tier": 194 % 5}

def apply(context: str = "") -> dict:
    if not context and 194 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
