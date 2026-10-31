"""Character peak 0400.
"""
from __future__ import annotations

ID = "character_peak_0400"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 400, "tier": 400 % 5}

def apply(context: str = "") -> dict:
    if not context and 400 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
