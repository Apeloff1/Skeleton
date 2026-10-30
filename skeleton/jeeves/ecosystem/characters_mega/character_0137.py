"""Character mega 0137.
"""
from __future__ import annotations

ID = "character_mega_0137"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 137, "tier": 137 % 5}

def apply(context: str = "") -> dict:
    if not context and 137 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
