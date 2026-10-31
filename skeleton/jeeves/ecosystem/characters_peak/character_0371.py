"""Character peak 0371.
"""
from __future__ import annotations

ID = "character_peak_0371"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 371, "tier": 371 % 5}

def apply(context: str = "") -> dict:
    if not context and 371 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
