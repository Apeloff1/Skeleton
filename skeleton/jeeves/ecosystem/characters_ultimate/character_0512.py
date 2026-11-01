"""Character ultimate 0512.
"""
from __future__ import annotations

ID = "character_ultimate_0512"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 512, "tier": 512 % 5}

def apply(context: str = "") -> dict:
    if not context and 512 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
