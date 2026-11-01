"""Character ultimate 0830.
"""
from __future__ import annotations

ID = "character_ultimate_0830"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 830, "tier": 830 % 5}

def apply(context: str = "") -> dict:
    if not context and 830 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
