"""Character mega 0119.
"""
from __future__ import annotations

ID = "character_mega_0119"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 119, "tier": 119 % 5}

def apply(context: str = "") -> dict:
    if not context and 119 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
