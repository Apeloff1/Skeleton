"""Character peak 0427.
"""
from __future__ import annotations

ID = "character_peak_0427"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 427, "tier": 427 % 5}

def apply(context: str = "") -> dict:
    if not context and 427 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
