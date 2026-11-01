"""Character ultimate 0835.
"""
from __future__ import annotations

ID = "character_ultimate_0835"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 835, "tier": 835 % 5}

def apply(context: str = "") -> dict:
    if not context and 835 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
