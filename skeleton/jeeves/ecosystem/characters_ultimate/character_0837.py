"""Character ultimate 0837.
"""
from __future__ import annotations

ID = "character_ultimate_0837"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 837, "tier": 837 % 5}

def apply(context: str = "") -> dict:
    if not context and 837 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
