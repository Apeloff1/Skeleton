"""Character peak 0422.
"""
from __future__ import annotations

ID = "character_peak_0422"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 422, "tier": 422 % 5}

def apply(context: str = "") -> dict:
    if not context and 422 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
